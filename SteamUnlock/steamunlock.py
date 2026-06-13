#!/usr/bin/env python3
"""
SteamUnlock v1.0 - Unified Steam Manifest Tool
Merges features from: Manifest2Lua, ManifestDownload, Onekey, SteamToolbox

Features:
  - Search games by name or AppID
  - Download manifests from 5 GitHub repos with CDN mirror fallback
  - Auto-install manifests + Lua scripts to Steam
  - Bulk unlock from AppID list file
  - Dump depot decryption keys from local depotcache
  - GitHub token support (5000 req/hr vs 60 without)
  - Restart Steam
  - Embedded depot key fallback lookup
"""

import asyncio
import aiohttp
import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Constants ────────────────────────────────────────────────────────────────

VERSION = "1.0.0"
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

# GitHub repos searched in priority order (same list as Onekey/SteamToolbox)
GITHUB_REPOS = [
    # ManifestHub forks (large curated collections)
    "SteamAutoCracks/ManifestHub",
    "ikun0014/ManifestHub",
    # ManifestAutoUpdate forks (auto-updated community uploads)
    "Masaiki/ManifestAutoUpdate",
    "Auiowu/ManifestAutoUpdate",
    "tymolu233/ManifestAutoUpdate-fix",
    "wxy1343/ManifestAutoUpdate",
    "hansaes/ManifestAutoUpdate",
    "cyao2q/ManifestAutoUpdate",
    "reindex-ot/ManifestAutoUpdate",
    "isKoi/ManifestAutoUpdate",
    "Cyberbolt/ManifestAutoUpdate",
    # Other community repos
    "Fairyvmos/bruh-hub",
    "ManifestAutoUpdate/ManifestAutoUpdate",
    "Cracko298/ManifestHub",
]

# CDN mirrors for raw file downloads (tried in order, with retry)
CDN_TEMPLATES = [
    "https://jsdelivr.pai233.top/gh/{repo}@{sha}/{path}",
    "https://cdn.jsdmirror.com/gh/{repo}@{sha}/{path}",
    "https://raw.gitmirror.com/{repo}/{sha}/{path}",
    "https://raw.dgithub.xyz/{repo}/{sha}/{path}",
    "https://gh.akass.cn/{repo}/{sha}/{path}",
    "https://raw.githubusercontent.com/{repo}/{sha}/{path}",
]

GITHUB_API    = "https://api.github.com"
STEAM_SEARCH  = "https://store.steampowered.com/api/storesearch/?term={term}&l=english&cc=US"
STEAM_DETAILS = "https://store.steampowered.com/api/appdetails?appids={appid}"

DEFAULT_CONFIG = {
    "github_token": "",
    "steam_path": "",
    "output_mode": "auto",  # "auto" = install into Steam dirs, "local" = save folder here
    "language": "en",
}

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

def load_env_token() -> str:
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip().upper() == "GITHUB_TOKEN":
                        return v.strip().strip('"').strip("'")
        except Exception:
            pass
    return os.environ.get("GITHUB_TOKEN", "")

def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    env_tok = load_env_token()
    if env_tok and not cfg.get("github_token"):
        cfg["github_token"] = env_tok
    return cfg

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ─── Steam Path Detection ─────────────────────────────────────────────────────

def get_steam_path(cfg: dict) -> Optional[Path]:
    if cfg.get("steam_path"):
        p = Path(cfg["steam_path"])
        if p.exists():
            return p

    # Windows Registry
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam")
        val, _ = winreg.QueryValueEx(key, "InstallPath")
        winreg.CloseKey(key)
        p = Path(val)
        if p.exists():
            return p
    except Exception:
        pass

    # Common fallback locations
    for p in [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]:
        if p.exists():
            return p

    return None

# ─── VDF Text Parser ──────────────────────────────────────────────────────────

def parse_vdf_keys(content: str) -> Dict[str, str]:
    """
    Parse a text-format VDF (Key.vdf / config.vdf) and return {depotID: decryptionKey}.
    Handles the standard depot key file format:
        "depots" { "12345" { "DecryptionKey" "aabbcc..." } }
    """
    keys: Dict[str, str] = {}
    current_depot: Optional[str] = None
    depth = 0

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        if line == "{":
            depth += 1
            continue
        if line == "}":
            depth -= 1
            if depth <= 1:
                current_depot = None
            continue

        # Quoted string token(s) on one line
        tokens = re.findall(r'"([^"]*)"', line)
        if len(tokens) == 1:
            # standalone key (section header) - could be a depot ID
            if tokens[0].isdigit():
                current_depot = tokens[0]
        elif len(tokens) == 2:
            key, val = tokens
            if key.lower() == "decryptionkey" and current_depot:
                keys[current_depot] = val

    return keys

# ─── Embedded Depot Key Fallback ─────────────────────────────────────────────

_depot_keys_cache: Optional[Dict[str, str]] = None

def load_depot_keys() -> Dict[str, str]:
    """Lazily load the embedded depotkeys.json from SteamToolbox assets."""
    global _depot_keys_cache
    if _depot_keys_cache is not None:
        return _depot_keys_cache

    candidates = [
        SCRIPT_DIR / "assets" / "depotkeys.json",
        SCRIPT_DIR.parent / "SteamToolbox" / "assets" / "data" / "depotkeys.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    _depot_keys_cache = json.load(f)
                log.debug(f"Loaded {len(_depot_keys_cache)} depot keys from {p.name}")
                return _depot_keys_cache
            except Exception:
                pass

    _depot_keys_cache = {}
    return _depot_keys_cache

# ─── GitHub Rate Limit ────────────────────────────────────────────────────────

async def get_rate_limit(session: aiohttp.ClientSession, token: str) -> dict:
    headers = {"Authorization": f"token {token}"} if token else {}
    try:
        async with session.get(
            f"{GITHUB_API}/rate_limit", headers=headers, ssl=False,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status == 200:
                return (await r.json()).get("rate", {})
    except Exception:
        pass
    return {}

def print_rate_limit(rl: dict):
    if not rl:
        return
    remaining = rl.get("remaining", "?")
    limit = rl.get("limit", "?")
    reset_ts = rl.get("reset", 0)
    reset_str = datetime.datetime.fromtimestamp(reset_ts).strftime("%H:%M:%S") if reset_ts else "?"
    log.info(f"  GitHub API: {remaining}/{limit} requests remaining (resets {reset_str})")
    if rl.get("remaining", 1) == 0:
        log.error("  ✗ Rate limit exhausted. Add a GitHub token to config.json for 5000 req/hr.")
    elif rl.get("limit", 60) <= 60:
        log.warning("  ⚠ Using unauthenticated API (60 req/hr). Set github_token in config.json.")

# ─── Game Search ─────────────────────────────────────────────────────────────

async def search_games(term: str) -> List[dict]:
    """Search Steam store. Returns list of {appid, name}."""
    url = STEAM_SEARCH.format(term=term)
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    # Steam storesearch returns {"items": [{"id":730,"name":"...","tiny_image":"..."}]}
                    return [{"appid": str(i["id"]), "name": i["name"]}
                            for i in data.get("items", [])]
        except Exception as e:
            log.debug(f"Search error: {e}")
    return []

async def resolve_game_name(app_id: str) -> str:
    games = await search_games(app_id)
    if games:
        return games[0].get("name") or ""
    return ""

# ─── File Download via CDN Mirrors ────────────────────────────────────────────

async def download_raw(
    session: aiohttp.ClientSession, repo: str, sha: str, path: str
) -> Optional[bytes]:
    """Try each CDN mirror in order, 2 attempts each."""
    for template in CDN_TEMPLATES:
        url = template.format(repo=repo, sha=sha, path=path)
        for _ in range(2):
            try:
                async with session.get(
                    url, ssl=False, timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    if r.status == 200:
                        return await r.read()
            except Exception:
                pass
    return None

# ─── GitHub Manifest Fetching ─────────────────────────────────────────────────

async def fetch_manifests(
    app_id: str, github_token: str = ""
) -> Tuple[List[dict], Dict[str, str]]:
    """
    Search all GitHub repos concurrently for this AppID branch.
    Returns (manifest_list, depot_keys) from the repository branch with the latest commit date.
    """
    gh_headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        gh_headers["Authorization"] = f"token {github_token}"

    async with aiohttp.ClientSession(headers=gh_headers) as session:
        rl = await get_rate_limit(session, github_token)
        print_rate_limit(rl)
        if rl and rl.get("remaining", 1) == 0:
            return [], {}

        async def check_repo(repo):
            try:
                async with session.get(
                    f"{GITHUB_API}/repos/{repo}/branches/{app_id}",
                    ssl=False, timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status == 200:
                        branch = await r.json()
                        date_str = branch.get("commit", {}).get("commit", {}).get("author", {}).get("date", "")
                        return repo, branch, date_str
            except Exception:
                pass
            return repo, None, ""

        async def discover_repos() -> List[str]:
            """Search GitHub for any repo containing manifests for this AppID."""
            try:
                query = f"{app_id}+in:path+extension:manifest"
                async with session.get(
                    f"{GITHUB_API}/search/code?q={query}&per_page=10",
                    ssl=False, timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status != 200:
                        return []
                    data = await r.json()
                    found = []
                    for item in data.get("items", []):
                        rn = item.get("repository", {}).get("full_name", "")
                        if rn and rn not in GITHUB_REPOS:
                            found.append(rn)
                    if found:
                        log.info(f"  Dynamic search found extra repo(s): {', '.join(found)}")
                    return found
            except Exception:
                return []

        repos_to_check = list(GITHUB_REPOS)
        if github_token:  # search API needs auth to be reliable
            repos_to_check.extend(await discover_repos())

        log.info(f"Checking {len(repos_to_check)} manifest source(s)...")
        tasks = [check_repo(repo) for repo in repos_to_check]
        results = await asyncio.gather(*tasks)

        # Filter out repos where the branch wasn't found
        valid_results = [r for r in results if r[1] is not None]
        if not valid_results:
            return [], {}

        # Sort by commit date descending (newest first)
        valid_results.sort(key=lambda x: x[2], reverse=True)

        for repo, branch, date in valid_results:
            log.info(f"  ✓ Using {repo} (newest version, updated {date})")
            sha = branch["commit"]["sha"]
            tree_url = branch["commit"]["commit"]["tree"]["url"]

            try:
                async with session.get(
                    tree_url, ssl=False, timeout=aiohttp.ClientTimeout(total=15)
                ) as r2:
                    if r2.status != 200:
                        continue
                    tree = (await r2.json()).get("tree", [])
            except Exception:
                continue

            depot_keys: Dict[str, str] = {}
            manifests: List[dict] = []

            # Download VDF key file first (Key.vdf / config.vdf)
            vdf_names = {"key.vdf", "config.vdf"}
            for item in tree:
                if item["path"].lower() in vdf_names:
                    raw = await download_raw(session, repo, sha, item["path"])
                    if raw:
                        try:
                            depot_keys = parse_vdf_keys(raw.decode("utf-8", errors="ignore"))
                            log.info(f"  ✓ Parsed {len(depot_keys)} depot key(s) from {item['path']}")
                        except Exception:
                            pass
                    break

            # Collect manifest entries
            for item in tree:
                if item["path"].endswith(".manifest"):
                    name = item["path"].replace(".manifest", "")
                    parts = name.split("_", 1)
                    if len(parts) == 2:
                        manifests.append({
                            "depot_id":   parts[0],
                            "manifest_id": parts[1],
                            "sha":  sha,
                            "repo": repo,
                            "path": item["path"],
                        })

            if manifests:
                return manifests, depot_keys

    return [], {}

# ─── Manifest Download ────────────────────────────────────────────────────────

async def download_manifests(manifests: List[dict], dest_dir: Path) -> int:
    """Download manifest files to dest_dir. Returns count of files saved."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(10)
    saved = 0

    async def dl_one(m: dict):
        nonlocal saved
        save_path = dest_dir / m["path"]
        if save_path.exists():
            log.info(f"  ✓ Exists: {m['path']}")
            saved += 1
            return
        async with sem:
            async with aiohttp.ClientSession() as session:
                data = await download_raw(session, m["repo"], m["sha"], m["path"])
            if data:
                save_path.write_bytes(data)
                log.info(f"  ✓ Downloaded: {m['path']}")
                saved += 1
            else:
                log.error(f"  ✗ Failed: {m['path']}")

    await asyncio.gather(*[dl_one(m) for m in manifests])
    return saved

# ─── Lua Script Generation ────────────────────────────────────────────────────

def build_lua(app_id: str, manifests: List[dict], depot_keys: Dict[str, str]) -> str:
    """
    Generate a SteamTools Lua unlock script.
    Format used by stplug-in/{appID}.lua
    """
    lines = [f"addappid({app_id})"]
    seen: set = set()

    for m in manifests:
        did = m["depot_id"]
        mid = m["manifest_id"]

        if did not in seen:
            seen.add(did)
            # Key priority: VDF-parsed → embedded depotkeys.json → no key
            key = depot_keys.get(did) or load_depot_keys().get(did, "")
            if key:
                lines.append(f'addappid({did},1,"{key}")')
            else:
                lines.append(f"addappid({did},1)")

        lines.append(f'setManifestid({did},"{mid}",0)')

    return "\n".join(lines)

# ─── Dump Keys from depotcache ────────────────────────────────────────────────

def dump_keys_from_depotcache(depotcache: Path) -> Dict[str, str]:
    """
    Parse all .vdf files in depotcache and extract DecryptionKey values.
    Mirrors the ManifestDownload 'dumpkey' command.
    """
    all_keys: Dict[str, str] = {}
    vdf_files = list(depotcache.glob("**/*.vdf"))

    if not vdf_files:
        log.warning(f"No .vdf files found in {depotcache}")
        return all_keys

    log.info(f"Scanning {len(vdf_files)} VDF file(s)...")

    for vdf_path in vdf_files:
        try:
            content = vdf_path.read_text(encoding="utf-8", errors="ignore")
            keys = parse_vdf_keys(content)
            if keys:
                all_keys.update(keys)
                log.info(f"  {vdf_path.name}: {len(keys)} key(s)")
        except Exception as e:
            log.warning(f"  ✗ {vdf_path.name}: {e}")

    return all_keys

# ─── Steam Restart ────────────────────────────────────────────────────────────

def restart_steam(steam_path: Optional[Path]):
    log.info("Stopping Steam...")
    subprocess.run(["taskkill", "/F", "/IM", "steam.exe"], capture_output=True)
    time.sleep(2)

    if steam_path:
        exe = steam_path / "steam.exe"
        if exe.exists():
            log.info("Starting Steam...")
            subprocess.Popen([str(exe)])
            return

    log.warning("Could not find steam.exe. Please start Steam manually.")

# ─── Core Unlock Flow ─────────────────────────────────────────────────────────

async def unlock(app_id: str, cfg: dict, force_local: bool = False) -> bool:
    """Full unlock pipeline for one AppID."""
    log.info(f"\n{'─'*52}")
    log.info(f"  Unlocking AppID: {app_id}")
    log.info(f"{'─'*52}")

    manifests, depot_keys = await fetch_manifests(app_id, cfg.get("github_token", ""))

    if not manifests:
        log.error(f"✗ No manifests found for AppID {app_id}")
        return False

    steam_path  = get_steam_path(cfg)
    use_auto    = (cfg.get("output_mode", "auto") == "auto") and steam_path and not force_local

    if use_auto:
        depotcache  = steam_path / "depotcache"
        stplugin    = steam_path / "config" / "stplug-in"
        stplugin.mkdir(parents=True, exist_ok=True)

        log.info(f"\nInstalling manifests → {depotcache}")
        count = await download_manifests(manifests, depotcache)

        lua      = build_lua(app_id, manifests, depot_keys)
        lua_path = stplugin / f"{app_id}.lua"
        lua_path.write_text(lua, encoding="utf-8")

        log.info(f"\n✅ {count}/{len(manifests)} manifests installed.")
        log.info(f"   Lua: {lua_path}")
        log.info(f"   Restart Steam to apply.")
    else:
        name       = await resolve_game_name(app_id)
        folder     = SCRIPT_DIR / (f"[{app_id}]{name}" if name else f"[{app_id}]")

        log.info(f"\nSaving to local folder: {folder.name}")
        count = await download_manifests(manifests, folder)

        lua      = build_lua(app_id, manifests, depot_keys)
        lua_path = folder / f"{app_id}.lua"
        lua_path.write_text(lua, encoding="utf-8")

        log.info(f"\n✅ {count}/{len(manifests)} manifests saved.")
        log.info(f"   Lua: {lua_path}")
        if steam_path:
            log.info(f"\n   To install manually:")
            log.info(f"   1. Copy *.manifest files → {steam_path / 'depotcache'}")
            log.info(f"   2. Copy {app_id}.lua    → {steam_path / 'config' / 'stplug-in'}")
        else:
            log.info(f"\n   Drag all files in '{folder.name}' onto the SteamTools floating window.")

    return True

# ─── Commands ─────────────────────────────────────────────────────────────────

async def cmd_search(args, cfg):
    term = " ".join(args.terms)
    log.info(f"Searching: {term}")
    games = await search_games(term)
    if not games:
        log.info("No results.")
        return
    print(f"\n  {'#':<4} {'AppID':<12} Name")
    print(f"  {'─'*4} {'─'*12} {'─'*30}")
    for i, g in enumerate(games[:25], 1):
        name = g.get("schinese_name") or g.get("name") or "?"
        print(f"  {i:<4} {g['appid']:<12} {name}")


async def cmd_unlock(args, cfg):
    force_local = getattr(args, "local", False)
    results = {"ok": 0, "fail": 0}
    for app_id in args.appids:
        app_id = app_id.strip()
        if not app_id.isdigit():
            log.error(f"✗ Invalid AppID: {app_id}")
            results["fail"] += 1
            continue
        ok = await unlock(app_id, cfg, force_local=force_local)
        results["ok" if ok else "fail"] += 1
    if len(args.appids) > 1:
        log.info(f"\nTotal: {results['ok']} succeeded, {results['fail']} failed")


async def cmd_bulk(args, cfg):
    fp = Path(args.file)
    if not fp.exists():
        log.error(f"File not found: {fp}")
        return
    app_ids = [l.strip() for l in fp.read_text(encoding="utf-8").splitlines()
               if l.strip().isdigit()]
    if not app_ids:
        log.error("No valid AppIDs found in file.")
        return
    log.info(f"Bulk unlock: {len(app_ids)} AppIDs from {fp.name}")
    ok = fail = 0
    for app_id in app_ids:
        if await unlock(app_id, cfg):
            ok += 1
        else:
            fail += 1
    log.info(f"\nBulk complete: {ok} succeeded, {fail} failed")


async def cmd_dumpkeys(args, cfg):
    steam_path = get_steam_path(cfg)

    if getattr(args, "path", None):
        dc = Path(args.path)
    elif steam_path:
        dc = steam_path / "depotcache"
    else:
        log.error("No path specified and Steam not found. Use --path or set steam_path in config.")
        return

    if not dc.exists():
        log.error(f"Path not found: {dc}")
        return

    log.info(f"Scanning: {dc}")
    keys = dump_keys_from_depotcache(dc)
    if not keys:
        log.info("No depot keys found.")
        return

    out = Path(getattr(args, "output", None) or "keys.txt")
    with open(out, "w", encoding="utf-8") as f:
        for did, k in sorted(keys.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            f.write(f'"{did}":"{k}"\n')
    log.info(f"✓ Saved {len(keys)} depot keys to {out}")


async def cmd_restart(args, cfg):
    steam_path = get_steam_path(cfg)
    if not steam_path:
        log.error("Steam not found. Set steam_path in config.json")
        return
    confirm = input("Restart Steam now? [y/N]: ").strip().lower()
    if confirm == "y":
        restart_steam(steam_path)


async def cmd_config_show(args, cfg):
    print(f"\nConfig: {CONFIG_FILE}\n")
    print(json.dumps(cfg, indent=2))
    steam = get_steam_path(cfg)
    print(f"\nResolved Steam path: {steam or '(not found)'}")

    if getattr(args, "set", None):
        for pair in args.set:
            if "=" in pair:
                k, v = pair.split("=", 1)
                cfg[k.strip()] = v.strip()
                log.info(f"  Set {k.strip()} = {v.strip()}")
        save_config(cfg)
        log.info("Config saved.")


# ─── Interactive Menu ─────────────────────────────────────────────────────────

async def interactive(cfg: dict):
    steam_path = get_steam_path(cfg)
    token      = cfg.get("github_token", "")

    while True:
        print(f"\n{'═'*54}")
        print(f"  SteamUnlock v{VERSION}")
        print(f"{'═'*54}")
        print(f"  Steam : {steam_path or '(not found)'}")
        print(f"  Token : {'✓ set' if token else '✗ not set  (60 req/hr)'}")
        print(f"  Mode  : {cfg.get('output_mode', 'auto')}")
        print(f"{'─'*54}")
        print("  1  Unlock by AppID")
        print("  2  Search games by name")
        print("  3  Bulk unlock from file")
        print("  4  Dump depot keys from depotcache")
        print("  5  Restart Steam")
        print("  6  Edit config")
        print("  0  Exit")
        print()
        choice = input("  Choice: ").strip()

        if choice == "0":
            break

        elif choice == "1":
            raw = input("  AppID(s) - space separated: ").strip()
            for app_id in raw.split():
                if app_id.isdigit():
                    await unlock(app_id, cfg)
                else:
                    log.error(f"  Invalid AppID: {app_id}")

        elif choice == "2":
            term = input("  Game name: ").strip()
            if not term:
                continue
            games = await search_games(term)
            if not games:
                log.info("  No results.")
                continue
            print(f"\n  {'#':<4} {'AppID':<12} Name")
            print(f"  {'─'*4} {'─'*12} {'─'*30}")
            for i, g in enumerate(games[:20], 1):
                name = g.get("name") or "?"
                print(f"  {i:<4} {g['appid']:<12} {name}")
            print()
            sub = input("  Enter # to unlock, or Enter to skip: ").strip()
            if sub.isdigit() and 1 <= int(sub) <= len(games):
                g = games[int(sub) - 1]
                await unlock(str(g["appid"]), cfg)

        elif choice == "3":
            fp = input("  Path to AppID list file: ").strip().strip('"')
            fp_path = Path(fp)
            if not fp_path.exists():
                log.error(f"  File not found: {fp}")
                continue
            ids = [l.strip() for l in fp_path.read_text().splitlines() if l.strip().isdigit()]
            log.info(f"  Processing {len(ids)} AppIDs...")
            ok = fail = 0
            for app_id in ids:
                if await unlock(app_id, cfg):
                    ok += 1
                else:
                    fail += 1
            log.info(f"  Done: {ok} succeeded, {fail} failed")

        elif choice == "4":
            dc_default = str(steam_path / "depotcache") if steam_path else ""
            prompt = f"  Depotcache path [{dc_default}]: " if dc_default else "  Depotcache path: "
            dc_input = input(prompt).strip().strip('"') or dc_default
            if not dc_input:
                log.error("  No path provided.")
                continue
            dc = Path(dc_input)
            if not dc.exists():
                log.error(f"  Path not found: {dc}")
                continue
            keys = dump_keys_from_depotcache(dc)
            if keys:
                out = SCRIPT_DIR / "keys.txt"
                with open(out, "w", encoding="utf-8") as f:
                    for did, k in sorted(keys.items()):
                        f.write(f'"{did}":"{k}"\n')
                log.info(f"  ✓ Saved {len(keys)} keys → {out}")
            else:
                log.info("  No keys found.")

        elif choice == "5":
            if not steam_path:
                log.error("  Steam not found.")
                continue
            confirm = input("  Restart Steam? [y/N]: ").strip().lower()
            if confirm == "y":
                restart_steam(steam_path)

        elif choice == "6":
            print(f"\n  Config file: {CONFIG_FILE}")
            print(json.dumps(cfg, indent=2))
            print("\n  Available keys:")
            print("    github_token  - GitHub personal token (empty = 60 req/hr limit)")
            print("    steam_path    - Full path to Steam install (auto-detected if blank)")
            print("    output_mode   - 'auto' (install to Steam) or 'local' (save here)")
            print()
            k = input("  Key to change (or Enter to skip): ").strip()
            if k:
                v = input(f"  New value for '{k}': ").strip()
                cfg[k] = v
                save_config(cfg)
                # Refresh derived values
                steam_path = get_steam_path(cfg)
                token      = cfg.get("github_token", "")
                log.info("  ✓ Saved.")

        else:
            log.info("  Unknown option.")

# ─── CLI Argument Parser ──────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="steamunlock",
        description=f"SteamUnlock v{VERSION} - Unified Steam manifest tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  steamunlock                        # interactive menu
  steamunlock unlock 730             # unlock CS2
  steamunlock unlock 730 570 440     # unlock multiple games
  steamunlock unlock 730 --local     # save to local folder instead of Steam
  steamunlock search "elden ring"    # search by name
  steamunlock bulk appids.txt        # unlock all IDs in file
  steamunlock dumpkeys               # extract keys from Steam depotcache
  steamunlock dumpkeys --path D:\\depotcache --output keys.txt
  steamunlock restart                # restart Steam
  steamunlock config                 # show config
  steamunlock config --set github_token=ghp_xxx output_mode=auto
        """,
    )
    p.add_argument("--version", action="version", version=f"SteamUnlock {VERSION}")
    sub = p.add_subparsers(dest="command")

    # search
    s = sub.add_parser("search", help="Search games by name")
    s.add_argument("terms", nargs="+")

    # unlock
    u = sub.add_parser("unlock", help="Unlock game(s) by AppID")
    u.add_argument("appids", nargs="+", help="AppID(s) to unlock")
    u.add_argument("--local", action="store_true", help="Save to local folder instead of auto-install")

    # bulk
    b = sub.add_parser("bulk", help="Unlock many games from a file (one AppID per line)")
    b.add_argument("file")

    # dumpkeys
    d = sub.add_parser("dumpkeys", help="Extract depot keys from depotcache VDF files")
    d.add_argument("--path", help="Path to depotcache directory (default: auto-detect)")
    d.add_argument("--output", help="Output file (default: keys.txt)")

    # restart
    sub.add_parser("restart", help="Restart Steam")

    # config
    c = sub.add_parser("config", help="Show or edit config")
    c.add_argument("--set", nargs="*", metavar="KEY=VALUE")

    return p

# ─── Entry Point ──────────────────────────────────────────────────────────────

async def _main():
    parser = build_parser()
    args   = parser.parse_args()
    cfg    = load_config()

    dispatch = {
        "search":   cmd_search,
        "unlock":   cmd_unlock,
        "bulk":     cmd_bulk,
        "dumpkeys": cmd_dumpkeys,
        "restart":  cmd_restart,
        "config":   cmd_config_show,
    }

    if args.command is None:
        await interactive(cfg)
    elif args.command in dispatch:
        await dispatch[args.command](args, cfg)
    else:
        parser.print_help()

def main():
    # Force UTF-8 output on Windows so box chars and Unicode names print correctly
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    asyncio.run(_main())

if __name__ == "__main__":
    main()
