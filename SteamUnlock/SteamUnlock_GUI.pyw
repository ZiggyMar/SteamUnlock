"""
SteamUnlock GUI - Single executable Steam manifest tool
"""

import asyncio
import aiohttp
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Core constants ───────────────────────────────────────────────────────────

VERSION     = "1.0.0"
SCRIPT_DIR  = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

GITHUB_REPOS = [
    "SteamAutoCracks/ManifestHub",
    "ikun0014/ManifestHub",
    "Auiowu/ManifestAutoUpdate",
    "tymolu233/ManifestAutoUpdate-fix",
    "wxy1343/ManifestAutoUpdate",
]

CDN_TEMPLATES = [
    "https://jsdelivr.pai233.top/gh/{repo}@{sha}/{path}",
    "https://cdn.jsdmirror.com/gh/{repo}@{sha}/{path}",
    "https://raw.gitmirror.com/{repo}/{sha}/{path}",
    "https://raw.dgithub.xyz/{repo}/{sha}/{path}",
    "https://gh.akass.cn/{repo}/{sha}/{path}",
    "https://raw.githubusercontent.com/{repo}/{sha}/{path}",
]

GITHUB_API   = "https://api.github.com"
STEAM_SEARCH = "https://store.steampowered.com/api/storesearch/?term={term}&l=english&cc=US"

DEFAULT_CONFIG = {
    "github_token": "",
    "steam_path": "",
    "output_mode": "auto",
}

# ─── Colors ───────────────────────────────────────────────────────────────────

BG        = "#1a1a2e"
BG2       = "#16213e"
BG3       = "#0f3460"
ACCENT    = "#e94560"
ACCENT2   = "#53c0f0"
TEXT      = "#eaeaea"
TEXT_DIM  = "#888"
GREEN     = "#4caf50"
YELLOW    = "#ffb300"
RED       = "#f44336"
ENTRY_BG  = "#0d1b2a"

# ─── Config ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ─── Steam path ───────────────────────────────────────────────────────────────

def get_steam_path(cfg: dict) -> Optional[Path]:
    if cfg.get("steam_path"):
        p = Path(cfg["steam_path"])
        if p.exists():
            return p
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
    for p in [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]:
        if p.exists():
            return p
    return None

# ─── VDF parser ───────────────────────────────────────────────────────────────

def parse_vdf_keys(content: str) -> Dict[str, str]:
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
        tokens = re.findall(r'"([^"]*)"', line)
        if len(tokens) == 1 and tokens[0].isdigit():
            current_depot = tokens[0]
        elif len(tokens) == 2:
            k, v = tokens
            if k.lower() == "decryptionkey" and current_depot:
                keys[current_depot] = v
    return keys

# ─── Depot keys fallback ──────────────────────────────────────────────────────

_depot_keys_cache: Optional[Dict[str, str]] = None

def load_depot_keys() -> Dict[str, str]:
    global _depot_keys_cache
    if _depot_keys_cache is not None:
        return _depot_keys_cache
    for p in [
        SCRIPT_DIR / "assets" / "depotkeys.json",
        SCRIPT_DIR.parent / "SteamToolbox" / "assets" / "data" / "depotkeys.json",
    ]:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    _depot_keys_cache = json.load(f)
                return _depot_keys_cache
            except Exception:
                pass
    _depot_keys_cache = {}
    return _depot_keys_cache

# ─── Core async functions ─────────────────────────────────────────────────────

async def search_games(term: str) -> List[dict]:
    url = STEAM_SEARCH.format(term=term)
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    return [{"appid": str(i["id"]), "name": i["name"]}
                            for i in data.get("items", [])]
        except Exception:
            pass
    return []

async def resolve_name(app_id: str) -> str:
    games = await search_games(app_id)
    return games[0]["name"] if games else ""

async def download_raw(session, repo, sha, path) -> Optional[bytes]:
    for tpl in CDN_TEMPLATES:
        url = tpl.format(repo=repo, sha=sha, path=path)
        for _ in range(2):
            try:
                async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status == 200:
                        return await r.read()
            except Exception:
                pass
    return None

async def fetch_manifests(app_id: str, token: str, log_cb) -> Tuple[List[dict], Dict[str, str]]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    async with aiohttp.ClientSession(headers=headers) as session:
        # Rate limit
        try:
            async with session.get(f"{GITHUB_API}/rate_limit", ssl=False,
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    rl = (await r.json()).get("rate", {})
                    rem = rl.get("remaining", "?")
                    lim = rl.get("limit", "?")
                    reset = datetime.datetime.fromtimestamp(rl.get("reset", 0)).strftime("%H:%M:%S")
                    log_cb(f"GitHub API: {rem}/{lim} requests remaining (resets {reset})", "dim")
                    if rl.get("remaining", 1) == 0:
                        log_cb("Rate limit hit. Add a GitHub token in Settings.", "error")
                        return [], {}
        except Exception:
            pass

        for repo in GITHUB_REPOS:
            log_cb(f"Checking {repo} ...", "dim")
            try:
                async with session.get(
                    f"{GITHUB_API}/repos/{repo}/branches/{app_id}",
                    ssl=False, timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status == 404:
                        continue
                    if r.status != 200:
                        continue
                    branch = await r.json()
            except Exception:
                continue

            if "commit" not in branch:
                continue

            sha      = branch["commit"]["sha"]
            tree_url = branch["commit"]["commit"]["tree"]["url"]
            date     = branch["commit"]["commit"]["author"]["date"]

            try:
                async with session.get(tree_url, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r2:
                    tree = (await r2.json()).get("tree", []) if r2.status == 200 else []
            except Exception:
                continue

            depot_keys: Dict[str, str] = {}
            manifests: List[dict] = []

            # VDF keys
            for item in tree:
                if item["path"].lower() in ("key.vdf", "config.vdf"):
                    raw = await download_raw(session, repo, sha, item["path"])
                    if raw:
                        try:
                            depot_keys = parse_vdf_keys(raw.decode("utf-8", errors="ignore"))
                            log_cb(f"Parsed {len(depot_keys)} depot key(s)", "dim")
                        except Exception:
                            pass
                    break

            # Manifests
            for item in tree:
                if item["path"].endswith(".manifest"):
                    parts = item["path"].replace(".manifest", "").split("_", 1)
                    if len(parts) == 2:
                        manifests.append({
                            "depot_id": parts[0], "manifest_id": parts[1],
                            "sha": sha, "repo": repo, "path": item["path"],
                        })

            if manifests:
                log_cb(f"Found in {repo} — {len(manifests)} manifest(s), updated {date[:10]}", "ok")
                return manifests, depot_keys

    return [], {}

async def download_manifests(manifests, dest_dir, log_cb) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(10)
    saved = 0

    async def dl_one(m):
        nonlocal saved
        save_path = dest_dir / m["path"]
        if save_path.exists():
            log_cb(f"Exists: {m['path']}", "dim")
            saved += 1
            return
        async with sem:
            async with aiohttp.ClientSession() as session:
                data = await download_raw(session, m["repo"], m["sha"], m["path"])
            if data:
                save_path.write_bytes(data)
                log_cb(f"Downloaded: {m['path']}", "ok")
                saved += 1
            else:
                log_cb(f"Failed: {m['path']}", "error")

    await asyncio.gather(*[dl_one(m) for m in manifests])
    return saved

def build_lua(app_id, manifests, depot_keys) -> str:
    lines = [f"addappid({app_id})"]
    seen: set = set()
    for m in manifests:
        did, mid = m["depot_id"], m["manifest_id"]
        if did not in seen:
            seen.add(did)
            key = depot_keys.get(did) or load_depot_keys().get(did, "")
            lines.append(f'addappid({did},1,"{key}")' if key else f"addappid({did},1)")
        lines.append(f'setManifestid({did},"{mid}",0)')
    return "\n".join(lines)

async def unlock_app(app_id: str, cfg: dict, log_cb) -> bool:
    log_cb(f"Unlocking AppID: {app_id}", "header")
    manifests, depot_keys = await fetch_manifests(app_id, cfg.get("github_token", ""), log_cb)

    if not manifests:
        log_cb(f"No manifests found for {app_id}", "error")
        return False

    steam_path = get_steam_path(cfg)
    use_auto   = cfg.get("output_mode", "auto") == "auto" and steam_path

    if use_auto:
        depotcache = steam_path / "depotcache"
        stplugin   = steam_path / "config" / "stplug-in"
        stplugin.mkdir(parents=True, exist_ok=True)
        log_cb(f"Installing to Steam depotcache...", "dim")
        count = await download_manifests(manifests, depotcache, log_cb)
        lua   = build_lua(app_id, manifests, depot_keys)
        lua_path = stplugin / f"{app_id}.lua"
        lua_path.write_text(lua, encoding="utf-8")
        log_cb(f"{count}/{len(manifests)} manifests installed. Lua: {lua_path.name}", "ok")
        log_cb("Restart Steam to apply.", "info")
    else:
        name   = await resolve_name(app_id)
        folder = SCRIPT_DIR / (f"[{app_id}]{name}" if name else f"[{app_id}]")
        log_cb(f"Saving to local folder: {folder.name}", "dim")
        count  = await download_manifests(manifests, folder, log_cb)
        lua    = build_lua(app_id, manifests, depot_keys)
        (folder / f"{app_id}.lua").write_text(lua, encoding="utf-8")
        log_cb(f"{count}/{len(manifests)} files saved to {folder.name}", "ok")
        if steam_path:
            log_cb(f"Copy *.manifest → {steam_path / 'depotcache'}", "info")
            log_cb(f"Copy {app_id}.lua → {steam_path / 'config' / 'stplug-in'}", "info")

    return True

def dump_keys_from_depotcache(dc: Path, log_cb) -> Dict[str, str]:
    all_keys: Dict[str, str] = {}
    vdf_files = list(dc.glob("**/*.vdf"))
    if not vdf_files:
        log_cb(f"No .vdf files found in {dc}", "warn")
        return all_keys
    log_cb(f"Scanning {len(vdf_files)} VDF file(s)...", "dim")
    for vdf_path in vdf_files:
        try:
            keys = parse_vdf_keys(vdf_path.read_text(encoding="utf-8", errors="ignore"))
            if keys:
                all_keys.update(keys)
                log_cb(f"{vdf_path.name}: {len(keys)} key(s)", "dim")
        except Exception as e:
            log_cb(f"Error reading {vdf_path.name}: {e}", "error")
    return all_keys

# ─── SteamTools registry toggles ──────────────────────────────────────────────
# These map to the real SteamTools kernel settings under HKCU\Software\Valve\Steamtools
# so the toggles in the menu actually control SteamTools behaviour.

ST_REG_PATH = r"Software\Valve\Steamtools"

def get_st_toggle(name: str) -> bool:
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ST_REG_PATH)
        v, _ = winreg.QueryValueEx(k, name)
        winreg.CloseKey(k)
        return bool(v)
    except Exception:
        return False

def set_st_toggle(name: str, value: bool) -> bool:
    try:
        import winreg
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, ST_REG_PATH)
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 1 if value else 0)
        winreg.CloseKey(k)
        return True
    except Exception:
        return False

def get_launch_with_steam() -> bool:
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run")
        winreg.QueryValueEx(k, "SteamUnlock")
        winreg.CloseKey(k)
        return True
    except Exception:
        return False

def set_launch_with_steam(value: bool) -> bool:
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                           winreg.KEY_SET_VALUE)
        if value:
            exe = sys.executable if getattr(sys, "frozen", False) else \
                  f'pythonw "{Path(__file__).parent / "SteamUnlock_GUI.pyw"}"'
            winreg.SetValueEx(k, "SteamUnlock", 0, winreg.REG_SZ, exe)
        else:
            try:
                winreg.DeleteValue(k, "SteamUnlock")
            except FileNotFoundError:
                pass
        winreg.CloseKey(k)
        return True
    except Exception:
        return False

# ─── SteamTools-style palette ─────────────────────────────────────────────────

ST_BG       = "#1e2127"   # panel background
ST_BG2      = "#262a31"   # card / row background
ST_MENU_BG  = "#23262b"   # menu background
ST_HOVER    = "#33373f"   # hover highlight
ST_TEXT     = "#e8eaed"
ST_DIM      = "#8b919b"
ST_ICON     = "#5aa9e6"   # icon accent (Steam blue)
ST_SEP      = "#34383f"
ST_GREEN    = "#5cb85c"
ST_OFF      = "#4a4f57"
ST_ACCENT   = "#1a9fff"
KEY_COLOR   = "#ff00ff"   # transparency key for the floating icon

ICON_SIZE   = 78          # floating icon diameter (px)


# ─── Custom dark fly-out menu (SteamTools style) ──────────────────────────────

class MenuController:
    """SteamTools-style right-click menu built on the native tk.Menu (robust:
    handles hover, submenus, click-away and on-screen positioning automatically),
    themed dark with emoji icons and green check toggles."""

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self._menu = None
        self._toggle_vars = {}

    def _new_menu(self):
        return tk.Menu(
            self.root, tearoff=0,
            bg=ST_MENU_BG, fg=ST_TEXT,
            activebackground=ST_ACCENT, activeforeground="white",
            disabledforeground=ST_DIM,
            bd=0, relief="flat", activeborderwidth=0,
            font=("Microsoft YaHei UI", 10),
        )

    def _build(self, items):
        m = self._new_menu()
        for item in items:
            if item.get("sep"):
                m.add_separator()
                continue
            icon = item.get("icon", "")
            label = f"  {icon}  {item['label']}" if icon else f"  {item['label']}"
            if "submenu" in item:
                sub = self._build(item["submenu"])
                m.add_cascade(label=label + "    ", menu=sub)
            elif "toggle" in item:
                var = tk.BooleanVar(value=item["toggle"]["get"]())
                self._toggle_vars[item["label"]] = var

                def _cb(it=item, v=var):
                    it["toggle"]["set"](v.get())

                m.add_checkbutton(
                    label=label, variable=var, command=_cb,
                    onvalue=True, offvalue=False, selectcolor=ST_GREEN,
                )
            else:
                state = "normal" if item.get("enabled", True) else "disabled"
                m.add_command(label=label, state=state,
                              command=item.get("action") or (lambda: None))
        return m

    def show(self, items, x, y, open_left=True):
        self.close()
        self._toggle_vars = {}
        self._menu = self._build(items)
        # tk_popup auto-adjusts to stay on-screen and opens leftward near the
        # right edge, which matches the floating icon sitting bottom-right.
        try:
            self._menu.tk_popup(int(x), int(y))
        finally:
            self._menu.grab_release()

    def close(self):
        if self._menu is not None:
            try:
                self._menu.unpost()
                self._menu.destroy()
            except tk.TclError:
                pass
            self._menu = None


# ─── Workspace window (the actual tool) ───────────────────────────────────────

class Workspace:
    """The main tool surface, opened from the floating icon. SteamTools-dark themed."""

    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.win = None
        self._search_results: List[dict] = []

    def show(self, focus="search"):
        if self.win and tk.Toplevel.winfo_exists(self.win):
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
            return
        self._build()

    def _build(self):
        self.win = tk.Toplevel(self.app.root)
        self.win.title("SteamUnlock")
        self.win.configure(bg=ST_BG)
        self.win.geometry("760x560")
        self.win.minsize(680, 480)

        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("ST.Treeview", background="#14171c", foreground=ST_TEXT,
                        fieldbackground="#14171c", rowheight=26,
                        font=("Microsoft YaHei UI", 10), borderwidth=0)
        style.configure("ST.Treeview.Heading", background=ST_BG2, foreground=ST_DIM,
                        font=("Microsoft YaHei UI", 9, "bold"), borderwidth=0)
        style.map("ST.Treeview", background=[("selected", ST_ACCENT)],
                  foreground=[("selected", "white")])
        style.configure("ST.Vertical.TScrollbar", background=ST_BG2,
                        troughcolor=ST_BG, arrowcolor=ST_DIM, borderwidth=0)

        # Header
        header = tk.Frame(self.win, bg="#16191e", height=46)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Canvas(header, width=24, height=24, bg="#16191e",
                  highlightthickness=0).pack(side="left", padx=(14, 8))
        tk.Label(header, text="SteamUnlock", bg="#16191e", fg=ST_TEXT,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        tk.Label(header, text=f"v{VERSION}", bg="#16191e", fg=ST_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=6)

        body = tk.Frame(self.win, bg=ST_BG)
        body.pack(fill="both", expand=True, padx=12, pady=10)

        left = tk.Frame(body, bg=ST_BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=ST_BG2)
        right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        self._build_search(left)
        self._build_quick(left)
        self._build_tools(left)
        self._build_log(right)

        # status
        sb = tk.Frame(self.win, bg="#16191e", height=24)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(sb, textvariable=self.status_var, bg="#16191e", fg=ST_DIM,
                 font=("Segoe UI", 9), anchor="w").pack(side="left", padx=12)
        steam = get_steam_path(self.cfg)
        tk.Label(sb, text=f"Steam: {steam or 'not found'}", bg="#16191e",
                 fg=ST_GREEN if steam else "#d9a441",
                 font=("Segoe UI", 9)).pack(side="right", padx=12)

    def _section(self, parent, title):
        card = tk.Frame(parent, bg=ST_BG2, padx=14, pady=12)
        card.pack(fill="x", pady=(0, 8))
        tk.Label(card, text=title, bg=ST_BG2, fg=ST_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        return card

    def _entry(self, parent):
        e = tk.Entry(parent, bg="#14171c", fg=ST_TEXT, insertbackground=ST_TEXT,
                     relief="flat", font=("Microsoft YaHei UI", 11), bd=0)
        return e

    def _btn(self, parent, text, cmd, accent=False):
        b = tk.Button(parent, text=text, command=cmd, bd=0, cursor="hand2",
                      bg=ST_ACCENT if accent else "#2f343c",
                      fg="white" if accent else ST_TEXT,
                      activebackground="#1688e0" if accent else "#3a4049",
                      activeforeground="white",
                      font=("Microsoft YaHei UI", 10, "bold" if accent else "normal"),
                      padx=14, pady=6)
        return b

    def _build_search(self, parent):
        card = self._section(parent, "SEARCH GAME")
        row = tk.Frame(card, bg=ST_BG2)
        row.pack(fill="x", pady=(6, 0))
        self.search_var = tk.StringVar()
        self.search_entry = self._entry(row)
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self._do_search())
        self._btn(row, "Search", self._do_search, accent=True).pack(side="left")

        tf = tk.Frame(card, bg=ST_BG2)
        tf.pack(fill="both", expand=True, pady=(10, 0))
        self.tree = ttk.Treeview(tf, columns=("appid", "name"), show="headings",
                                 height=7, selectmode="browse", style="ST.Treeview")
        self.tree.heading("appid", text="AppID", anchor="w")
        self.tree.heading("name", text="Name", anchor="w")
        self.tree.column("appid", width=90, stretch=False)
        self.tree.column("name", width=280, stretch=True)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview,
                            style="ST.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._unlock_selected())

        br = tk.Frame(card, bg=ST_BG2)
        br.pack(fill="x", pady=(8, 0))
        self._btn(br, "⬇  Unlock Selected", self._unlock_selected,
                  accent=True).pack(side="right")
        tk.Label(br, text="Double-click a row, or select → Unlock", bg=ST_BG2,
                 fg=ST_DIM, font=("Segoe UI", 9)).pack(side="left")

    def _build_quick(self, parent):
        card = self._section(parent, "QUICK UNLOCK BY APPID")
        row = tk.Frame(card, bg=ST_BG2)
        row.pack(fill="x", pady=(6, 0))
        self.quick_var = tk.StringVar()
        qe = self._entry(row)
        qe.configure(textvariable=self.quick_var)
        qe.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        qe.bind("<Return>", lambda e: self._do_quick())
        self._btn(row, "Unlock", self._do_quick).pack(side="left")

        row2 = tk.Frame(card, bg=ST_BG2)
        row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="Bulk (one AppID per line):", bg=ST_BG2, fg=ST_DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        self._btn(row2, "📂 Choose File…", self._do_bulk).pack(side="left", padx=8)

    def _build_tools(self, parent):
        card = self._section(parent, "TOOLS")
        row = tk.Frame(card, bg=ST_BG2)
        row.pack(fill="x", pady=(4, 0))
        self._btn(row, "🔑 Dump Keys", self.app.do_dump_keys).pack(side="left", padx=(0, 8))
        self._btn(row, "🔄 Restart Steam", self.app.do_restart_steam).pack(side="left", padx=(0, 8))
        self._btn(row, "⚙ Settings", self.app.open_settings).pack(side="left")

    def _build_log(self, parent):
        tk.Label(parent, text="LOG", bg=ST_BG2, fg=ST_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self.log_text = tk.Text(parent, bg="#14171c", fg=ST_TEXT, insertbackground=ST_TEXT,
                                relief="flat", font=("Consolas", 9), wrap="word",
                                state="disabled", bd=0, padx=8, pady=6)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log_text.tag_config("ok", foreground=ST_GREEN)
        self.log_text.tag_config("error", foreground="#f06363")
        self.log_text.tag_config("warn", foreground="#e0b341")
        self.log_text.tag_config("info", foreground=ST_ICON)
        self.log_text.tag_config("dim", foreground=ST_DIM)
        self.log_text.tag_config("header", foreground=ST_ACCENT, font=("Consolas", 9, "bold"))

    # logging that targets this workspace
    def log(self, msg, tag=""):
        def _do():
            if not (self.win and tk.Toplevel.winfo_exists(self.win)):
                return
            self.log_text.config(state="normal")
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] {msg}\n", tag or "")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.app.root.after(0, _do)

    def set_status(self, msg):
        self.app.root.after(0, lambda: self.status_var.set(msg)
                            if self.win and tk.Toplevel.winfo_exists(self.win) else None)

    # actions
    def _do_search(self):
        term = self.search_var.get().strip()
        if not term:
            return
        self.log(f'Searching: "{term}"', "header")

        def _done(results):
            self._search_results = results
            for r in self.tree.get_children():
                self.tree.delete(r)
            for g in results[:25]:
                self.tree.insert("", "end", values=(g["appid"], g["name"]))
            self.log(f"{len(results)} result(s)." if results else "No results.",
                     "ok" if results else "warn")

        self.app.run_async(search_games(term), _done)

    def _unlock_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a game", "Click a game in the list first.")
            return
        appid, name = self.tree.item(sel[0], "values")
        self.log(f"Unlocking {name} ({appid})", "header")
        self.app.start_unlock(str(appid), self)

    def _do_quick(self):
        appid = self.quick_var.get().strip()
        if not appid.isdigit():
            messagebox.showerror("Invalid", "AppID must be numbers only.")
            return
        self.log(f"Quick unlock: {appid}", "header")
        self.app.start_unlock(appid, self)

    def _do_bulk(self):
        fp = filedialog.askopenfilename(title="Select AppID list",
                                        filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not fp:
            return
        ids = [l.strip() for l in Path(fp).read_text().splitlines() if l.strip().isdigit()]
        if not ids:
            messagebox.showerror("Empty", "No valid AppIDs found.")
            return
        self.log(f"Bulk: {len(ids)} AppIDs", "header")

        async def _do():
            ok = fail = 0
            for a in ids:
                if await unlock_app(a, self.cfg, self.log):
                    ok += 1
                else:
                    fail += 1
            return ok, fail

        self.app.run_async(_do(), lambda r: self.log(
            f"Bulk done: {r[0]} ok, {r[1]} failed", "info"))


# ─── Floating icon application (main) ─────────────────────────────────────────

class FloatingApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.menu = MenuController(self)
        self.workspace = Workspace(self)
        self._busy = False
        self._drag = False

        self._build_icon()
        self.root.after(400, self._show_welcome)

    # ── floating icon window ──────────────────────────────────────────────────
    def _build_icon(self):
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # Position on the PRIMARY monitor work area (multi-monitor safe).
        # winfo_screenwidth() can return the full virtual desktop width across
        # all monitors, which would put the icon off on another screen.
        wa = self._primary_workarea()
        self.ix = wa[2] - ICON_SIZE - 40
        self.iy = wa[3] - ICON_SIZE - 60
        self.root.geometry(f"{ICON_SIZE}x{ICON_SIZE}+{self.ix}+{self.iy}")

        self.canvas = tk.Canvas(self.root, width=ICON_SIZE, height=ICON_SIZE,
                                bg="#0d1622", highlightthickness=0, bd=0)
        self.canvas.pack()
        # Force the override-redirect window to actually map and come to front.
        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(200, self._hide_from_taskbar)
        self._draw_icon()

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<Button-3>", self._on_right)
        self.canvas.bind("<Enter>", lambda e: self._draw_icon(hover=True))
        self.canvas.bind("<Leave>", lambda e: self._draw_icon(hover=False))

    def _primary_workarea(self):
        """Return (left, top, right, bottom) of the primary monitor work area."""
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030 -> primary monitor, minus taskbar
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
            if rect.right > rect.left and rect.bottom > rect.top:
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def _hide_from_taskbar(self):
        """Make the floating icon a tool window so it has no taskbar button."""
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            # SWP_NOMOVE|NOSIZE|NOZORDER|FRAMECHANGED to apply the new ex-style
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
        except Exception:
            pass

    def _draw_icon(self, hover=False):
        c = self.canvas
        c.delete("all")
        s = ICON_SIZE
        cx, cy = s / 2, s / 2
        # outer disc (Steam dark blue gradient feel)
        ring = ST_ACCENT if hover else "#316a96"
        c.create_oval(2, 2, s - 2, s - 2, fill="#16202d", outline=ring, width=3)
        c.create_oval(7, 7, s - 7, s - 7, outline="#1f3346", width=1)
        # Steam emblem: large ring (head) + inner dot + pipe to small node
        emblem = "#dfe7ee"
        r1 = s * 0.20
        # big ring upper-left of center
        bx, by = cx - s * 0.06, cy - s * 0.06
        c.create_oval(bx - r1, by - r1, bx + r1, by + r1, outline=emblem, width=4)
        c.create_oval(bx - r1 * 0.45, by - r1 * 0.45,
                      bx + r1 * 0.45, by + r1 * 0.45, fill=emblem, outline=emblem)
        # pipe to small node lower-right
        nx, ny = cx + s * 0.18, cy + s * 0.18
        c.create_line(bx + r1 * 0.4, by + r1 * 0.4, nx, ny, fill=emblem, width=4)
        r2 = s * 0.10
        c.create_oval(nx - r2, ny - r2, nx + r2, ny + r2, fill=emblem, outline=emblem)

    # ── welcome bubble ────────────────────────────────────────────────────────
    def _show_welcome(self):
        try:
            bub = tk.Toplevel(self.root)
            bub.overrideredirect(True)
            bub.attributes("-topmost", True)
            bub.configure(bg=ST_SEP)
            inner = tk.Frame(bub, bg="#2b2f36")
            inner.pack(padx=1, pady=1)
            tk.Label(inner,
                     text="Welcome Back. Double-click to open SteamUnlock,\nright-click for the menu.",
                     bg="#2b2f36", fg=ST_TEXT, font=("Microsoft YaHei UI", 9),
                     justify="left", padx=12, pady=8).pack()
            bub.update_idletasks()
            w = bub.winfo_reqwidth()
            h = bub.winfo_reqheight()
            x = self.root.winfo_x() - w - 10
            y = self.root.winfo_y() + (ICON_SIZE - h) // 2
            if x < 0:
                x = self.root.winfo_x() + ICON_SIZE + 10
            bub.geometry(f"+{x}+{y}")
            self.root.after(5000, lambda: bub.destroy() if bub.winfo_exists() else None)
        except tk.TclError:
            pass

    # ── icon interaction ──────────────────────────────────────────────────────
    def _on_press(self, e):
        self._drag = False
        self._sx, self._sy = e.x_root, e.y_root
        self._ox, self._oy = self.root.winfo_x(), self.root.winfo_y()

    def _on_motion(self, e):
        dx = e.x_root - self._sx
        dy = e.y_root - self._sy
        if abs(dx) > 4 or abs(dy) > 4:
            self._drag = True
        self.root.geometry(f"+{self._ox + dx}+{self._oy + dy}")

    def _on_release(self, e):
        pass

    def _on_double(self, e):
        if not self._drag:
            self.workspace.show()

    def _on_right(self, e):
        self.menu.show(self._menu_items(), e.x_root, e.y_root, open_left=True)

    # ── menu definition ───────────────────────────────────────────────────────
    def _menu_items(self):
        return [
            {"icon": "▶", "label": "Launch Steam", "action": self.do_launch_steam},
            {"sep": True},
            {"icon": "🔍", "label": "Search for Games",
             "action": lambda: self.workspace.show("search")},
            {"icon": "⬇", "label": "Unlock Game…",
             "action": lambda: self.workspace.show("quick")},
            {"icon": "📋", "label": "Bulk Unlock…", "action": self._menu_bulk},
            {"icon": "🔓", "label": "Unlock Solution", "submenu": [
                {"icon": "✔", "label": "Activate Unlock Mode",
                 "toggle": {"get": lambda: get_st_toggle("ActivateUnlockMode"),
                            "set": lambda v: set_st_toggle("ActivateUnlockMode", v)}},
                {"icon": "🔒", "label": "Always Stay Unlocked",
                 "toggle": {"get": lambda: get_st_toggle("AlwaysStayUnlocked"),
                            "set": lambda v: set_st_toggle("AlwaysStayUnlocked", v)}},
                {"icon": "🚀", "label": "Launch with Steam",
                 "toggle": {"get": get_launch_with_steam, "set": set_launch_with_steam}},
            ]},
            {"sep": True},
            {"icon": "🔑", "label": "Dump Depot Keys", "action": self.do_dump_keys},
            {"icon": "📁", "label": "Open Steam Folder", "action": self.do_open_steam_folder},
            {"icon": "🔄", "label": "Restart Steam", "action": self.do_restart_steam},
            {"icon": "⚙", "label": "Settings", "action": self.open_settings},
            {"sep": True},
            {"icon": "◳", "label": "Open Main Window", "action": self.workspace.show},
            {"icon": "⏻", "label": "Exit", "action": self.root.destroy},
        ]

    def _menu_bulk(self):
        self.workspace.show()
        self.root.after(150, self.workspace._do_bulk)

    # ── shared async runner ───────────────────────────────────────────────────
    def run_async(self, coro, done_cb=None):
        def _thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(coro)
                if done_cb:
                    self.root.after(0, lambda: done_cb(result))
            except Exception as e:
                self.root.after(0, lambda: self._toast(f"Error: {e}"))
            finally:
                loop.close()
                self._busy = False
        self._busy = True
        threading.Thread(target=_thread, daemon=True).start()

    def start_unlock(self, appid, ws=None):
        ws = ws or self.workspace
        if not (ws.win and tk.Toplevel.winfo_exists(ws.win)):
            ws.show()
        log_cb = ws.log
        ws.set_status(f"Unlocking {appid}…")
        self.run_async(unlock_app(appid, self.cfg, log_cb),
                       lambda ok: ws.set_status("Done" if ok else f"Failed: {appid}"))

    # ── quick toast ───────────────────────────────────────────────────────────
    def _toast(self, msg, ms=2500):
        try:
            t = tk.Toplevel(self.root)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            t.configure(bg=ST_SEP)
            tk.Label(t, text=msg, bg="#2b2f36", fg=ST_TEXT,
                     font=("Microsoft YaHei UI", 9), padx=14, pady=8).pack(padx=1, pady=1)
            t.update_idletasks()
            w = t.winfo_reqwidth()
            x = self.root.winfo_x() - w - 10
            y = self.root.winfo_y()
            if x < 0:
                x = self.root.winfo_x() + ICON_SIZE + 10
            t.geometry(f"+{x}+{y}")
            self.root.after(ms, lambda: t.destroy() if t.winfo_exists() else None)
        except tk.TclError:
            pass

    # ── menu actions ──────────────────────────────────────────────────────────
    def do_launch_steam(self):
        steam = get_steam_path(self.cfg)
        exe = steam / "steam.exe" if steam else None
        if exe and exe.exists():
            subprocess.Popen([str(exe)])
            self._toast("Launching Steam…")
        else:
            self._toast("Steam not found")

    def do_restart_steam(self):
        steam = get_steam_path(self.cfg)
        if not steam:
            self._toast("Steam not found")
            return
        if messagebox.askyesno("Restart Steam", "Close and restart Steam now?"):
            subprocess.run(["taskkill", "/F", "/IM", "steam.exe"], capture_output=True)
            time.sleep(2)
            exe = steam / "steam.exe"
            if exe.exists():
                subprocess.Popen([str(exe)])
                self._toast("Steam restarted")

    def do_open_steam_folder(self):
        steam = get_steam_path(self.cfg)
        if steam:
            subprocess.Popen(["explorer", str(steam)])
        else:
            self._toast("Steam not found")

    def do_dump_keys(self):
        steam = get_steam_path(self.cfg)
        default = str(steam / "depotcache") if steam else ""
        dc = filedialog.askdirectory(title="Select depotcache folder",
                                     initialdir=default or str(SCRIPT_DIR))
        if not dc:
            return
        self.workspace.show()
        self.workspace.log(f"Dumping keys from {dc}", "header")

        def _do():
            keys = dump_keys_from_depotcache(Path(dc), self.workspace.log)
            if keys:
                out = SCRIPT_DIR / "keys.txt"
                with open(out, "w", encoding="utf-8") as f:
                    for did, k in sorted(keys.items()):
                        f.write(f'"{did}":"{k}"\n')
                self.workspace.log(f"Saved {len(keys)} keys to {out}", "ok")
            else:
                self.workspace.log("No keys found.", "warn")

        threading.Thread(target=_do, daemon=True).start()

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("520x320")
        win.configure(bg=ST_BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.grab_set()

        def lbl(t):
            tk.Label(pad, text=t, bg=ST_BG, fg=ST_DIM,
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 2))

        def entry(v=""):
            e = tk.Entry(pad, bg="#14171c", fg=ST_TEXT, insertbackground=ST_TEXT,
                         relief="flat", font=("Segoe UI", 10), bd=0)
            e.pack(fill="x", ipady=6)
            e.insert(0, v)
            return e

        pad = tk.Frame(win, bg=ST_BG, padx=20, pady=16)
        pad.pack(fill="both", expand=True)

        lbl("GitHub Personal Token (optional — 5000 req/hr vs 60):")
        token_e = entry(self.cfg.get("github_token", ""))
        lbl("Steam Install Path (blank = auto-detect):")
        steam_e = entry(self.cfg.get("steam_path", ""))
        lbl("Output Mode:")
        mode_var = tk.StringVar(value=self.cfg.get("output_mode", "auto"))
        mf = tk.Frame(pad, bg=ST_BG)
        mf.pack(anchor="w", pady=(4, 0))
        for txt, val in [("Auto-install into Steam", "auto"), ("Save to local folder", "local")]:
            tk.Radiobutton(mf, text=txt, variable=mode_var, value=val, bg=ST_BG,
                           fg=ST_TEXT, selectcolor=ST_BG2, activebackground=ST_BG,
                           activeforeground=ST_TEXT).pack(side="left", padx=(0, 18))

        def save():
            self.cfg["github_token"] = token_e.get().strip()
            self.cfg["steam_path"] = steam_e.get().strip()
            self.cfg["output_mode"] = mode_var.get()
            save_config(self.cfg)
            self._toast("Settings saved")
            win.destroy()

        br = tk.Frame(pad, bg=ST_BG)
        br.pack(fill="x", pady=(16, 0))
        tk.Button(br, text="Save", command=save, bd=0, cursor="hand2", bg=ST_ACCENT,
                  fg="white", activebackground="#1688e0", activeforeground="white",
                  font=("Segoe UI", 10, "bold"), padx=16, pady=6).pack(side="right")
        tk.Button(br, text="Cancel", command=win.destroy, bd=0, cursor="hand2",
                  bg="#2f343c", fg=ST_TEXT, font=("Segoe UI", 10),
                  padx=14, pady=6).pack(side="right", padx=8)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    FloatingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
