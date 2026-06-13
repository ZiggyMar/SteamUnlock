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

# ─── GUI ──────────────────────────────────────────────────────────────────────

class SteamUnlockApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg  = load_config()
        self._search_results: List[dict] = []
        self._busy = False

        self._setup_window()
        self._build_ui()
        self._check_steam()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        self.root.title(f"SteamUnlock v{VERSION}")
        self.root.geometry("820x680")
        self.root.minsize(700, 560)
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        # ttk style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, borderwidth=0,
                        focuscolor=ACCENT, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=BG2, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Dim.TLabel", background=BG2, foreground=TEXT_DIM, font=("Segoe UI", 9))
        style.configure("Head.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 11, "bold"))
        style.configure("Status.TLabel", background=BG3, foreground=TEXT_DIM, font=("Segoe UI", 9))
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=("Segoe UI", 10, "bold"), borderwidth=0, padding=(14, 6))
        style.map("Accent.TButton",
                  background=[("active", "#c73652"), ("disabled", "#555")])
        style.configure("TButton", background=BG3, foreground=TEXT,
                        font=("Segoe UI", 10), borderwidth=0, padding=(12, 6))
        style.map("TButton",
                  background=[("active", "#1e4d70"), ("disabled", "#333")])
        style.configure("Treeview", background=ENTRY_BG, foreground=TEXT,
                        fieldbackground=ENTRY_BG, rowheight=26,
                        font=("Segoe UI", 10), borderwidth=0)
        style.configure("Treeview.Heading", background=BG3, foreground=TEXT,
                        font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Treeview", background=[("selected", BG3)], foreground=[("selected", ACCENT2)])
        style.configure("TEntry", fieldbackground=ENTRY_BG, foreground=TEXT,
                        insertcolor=TEXT, borderwidth=1, relief="flat")
        style.configure("TScrollbar", background=BG2, troughcolor=BG,
                        arrowcolor=TEXT_DIM, borderwidth=0)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=BG3, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="⚡  SteamUnlock", bg=BG3, fg=TEXT,
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=18, pady=8)
        tk.Label(header, text=f"v{VERSION}", bg=BG3, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side="left", pady=8)

        btn_settings = tk.Button(header, text="⚙ Settings", bg=BG3, fg=TEXT_DIM,
                                 font=("Segoe UI", 9), bd=0, cursor="hand2",
                                 activebackground=BG, activeforeground=TEXT,
                                 command=self._open_settings)
        btn_settings.pack(side="right", padx=16, pady=10)

        # ── Main body ─────────────────────────────────────────────────────────
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # Left column
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        # Right column (log)
        right = ttk.Frame(body, style="Card.TFrame")
        right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        self._build_search_panel(left)
        self._build_quick_panel(left)
        self._build_tools_panel(left)
        self._build_log_panel(right)

        # ── Status bar ────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Frame(self.root, bg=BG3, height=26)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        self.status_lbl = tk.Label(status_bar, textvariable=self.status_var,
                                   bg=BG3, fg=TEXT_DIM, font=("Segoe UI", 9),
                                   anchor="w")
        self.status_lbl.pack(side="left", padx=12, fill="y")
        self.steam_lbl = tk.Label(status_bar, text="", bg=BG3, fg=TEXT_DIM,
                                  font=("Segoe UI", 9), anchor="e")
        self.steam_lbl.pack(side="right", padx=12, fill="y")

    def _build_search_panel(self, parent):
        card = tk.Frame(parent, bg=BG2, padx=14, pady=12)
        card.pack(fill="x", pady=(0, 8))

        tk.Label(card, text="SEARCH GAME", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")

        row = tk.Frame(card, bg=BG2)
        row.pack(fill="x", pady=(6, 0))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(row, textvariable=self.search_var,
                                     bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                                     relief="flat", font=("Segoe UI", 11),
                                     bd=0)
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        self.search_entry.insert(0, "Game name or AppID...")
        self.search_entry.bind("<FocusIn>",  self._clear_placeholder)
        self.search_entry.bind("<FocusOut>", self._restore_placeholder)
        self.search_entry.bind("<Return>",   lambda e: self._do_search())

        self.btn_search = ttk.Button(row, text="Search", style="Accent.TButton",
                                     command=self._do_search)
        self.btn_search.pack(side="left")

        # Results table
        tree_frame = tk.Frame(card, bg=BG2)
        tree_frame.pack(fill="both", expand=True, pady=(10, 0))

        cols = ("appid", "name")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  height=7, selectmode="browse")
        self.tree.heading("appid", text="AppID",  anchor="w")
        self.tree.heading("name",  text="Name",   anchor="w")
        self.tree.column("appid", width=100, minwidth=80, stretch=False)
        self.tree.column("name",  width=300, minwidth=180, stretch=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._unlock_selected())

        # Unlock selected button
        btn_row = tk.Frame(card, bg=BG2)
        btn_row.pack(fill="x", pady=(8, 0))
        self.btn_unlock_sel = ttk.Button(btn_row, text="⬇  Unlock Selected Game",
                                          style="Accent.TButton",
                                          command=self._unlock_selected)
        self.btn_unlock_sel.pack(side="right")
        tk.Label(btn_row, text="Double-click a row or select and click →",
                 bg=BG2, fg=TEXT_DIM, font=("Segoe UI", 9)).pack(side="left")

    def _build_quick_panel(self, parent):
        card = tk.Frame(parent, bg=BG2, padx=14, pady=12)
        card.pack(fill="x", pady=(0, 8))

        tk.Label(card, text="QUICK UNLOCK BY APPID", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")

        row = tk.Frame(card, bg=BG2)
        row.pack(fill="x", pady=(6, 0))

        self.quick_var = tk.StringVar()
        quick_entry = tk.Entry(row, textvariable=self.quick_var,
                                bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                                relief="flat", font=("Segoe UI", 11), bd=0)
        quick_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        quick_entry.bind("<Return>", lambda e: self._do_quick_unlock())

        ttk.Button(row, text="Unlock", command=self._do_quick_unlock).pack(side="left")

        # Bulk row
        row2 = tk.Frame(card, bg=BG2)
        row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="Bulk (one AppID per line):", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Button(row2, text="📂 Choose File...", command=self._do_bulk).pack(side="left", padx=8)

    def _build_tools_panel(self, parent):
        card = tk.Frame(parent, bg=BG2, padx=14, pady=12)
        card.pack(fill="x", pady=(0, 8))

        tk.Label(card, text="TOOLS", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))

        row = tk.Frame(card, bg=BG2)
        row.pack(fill="x")

        ttk.Button(row, text="🔑 Dump Depot Keys",
                   command=self._do_dump_keys).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="🔄 Restart Steam",
                   command=self._do_restart_steam).pack(side="left", padx=(0, 8))

    def _build_log_panel(self, parent):
        tk.Label(parent, text="LOG", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10, pady=(10, 4))

        self.log_text = tk.Text(
            parent, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Consolas", 9), wrap="word",
            state="disabled", bd=0, padx=8, pady=6,
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        # Tag colors
        self.log_text.tag_config("ok",     foreground=GREEN)
        self.log_text.tag_config("error",  foreground=RED)
        self.log_text.tag_config("warn",   foreground=YELLOW)
        self.log_text.tag_config("info",   foreground=ACCENT2)
        self.log_text.tag_config("dim",    foreground=TEXT_DIM)
        self.log_text.tag_config("header", foreground=ACCENT, font=("Consolas", 9, "bold"))

        btn_clear = tk.Button(parent, text="Clear", bg=BG2, fg=TEXT_DIM,
                              bd=0, font=("Segoe UI", 9), cursor="hand2",
                              activebackground=BG2, activeforeground=TEXT,
                              command=self._clear_log)
        btn_clear.pack(anchor="e", padx=10, pady=(0, 8))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_placeholder(self, event):
        if self.search_entry.get() == "Game name or AppID...":
            self.search_entry.delete(0, "end")
            self.search_entry.config(fg=TEXT)

    def _restore_placeholder(self, event):
        if not self.search_entry.get():
            self.search_entry.insert(0, "Game name or AppID...")
            self.search_entry.config(fg=TEXT_DIM)

    def _check_steam(self):
        steam = get_steam_path(self.cfg)
        if steam:
            self.steam_lbl.config(text=f"Steam: {steam}", fg=GREEN)
            self.status_var.set("Steam found  |  Ready")
        else:
            self.steam_lbl.config(text="Steam: not found", fg=YELLOW)
            self.status_var.set("Steam not found — set path in Settings")

    def log(self, msg: str, tag: str = ""):
        def _do():
            self.log_text.config(state="normal")
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] {msg}\n", tag or "")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _do)

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _set_status(self, msg: str):
        self.root.after(0, lambda: self.status_var.set(msg))

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.root.after(0, lambda: (
            self.btn_search.config(state=state),
            self.btn_unlock_sel.config(state=state),
        ))

    def _run_async(self, coro, done_cb=None):
        """Run a coroutine in a background thread with its own event loop."""
        def _thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(coro)
                if done_cb:
                    self.root.after(0, lambda: done_cb(result))
            except Exception as e:
                self.log(f"Error: {e}", "error")
            finally:
                loop.close()
                self._set_busy(False)
        self._set_busy(True)
        threading.Thread(target=_thread, daemon=True).start()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _do_search(self):
        term = self.search_var.get().strip()
        if not term or term == "Game name or AppID...":
            return
        self.log(f'Searching: "{term}"', "header")

        async def _search():
            return await search_games(term)

        def _done(results):
            self._search_results = results
            for row in self.tree.get_children():
                self.tree.delete(row)
            if results:
                for g in results[:25]:
                    self.tree.insert("", "end", values=(g["appid"], g["name"]))
                self.log(f"{len(results)} result(s) found.", "ok")
            else:
                self.log("No results.", "warn")

        self._run_async(_search(), _done)

    def _unlock_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a game", "Click a game in the list first.")
            return
        vals   = self.tree.item(sel[0], "values")
        app_id = vals[0]
        name   = vals[1]
        self.log(f"Starting unlock: {name} ({app_id})", "header")
        self._start_unlock(app_id)

    def _do_quick_unlock(self):
        app_id = self.quick_var.get().strip()
        if not app_id:
            return
        if not app_id.isdigit():
            messagebox.showerror("Invalid", f'"{app_id}" is not a valid AppID (numbers only).')
            return
        self.log(f"Quick unlock: {app_id}", "header")
        self._start_unlock(app_id)

    def _start_unlock(self, app_id: str):
        if self._busy:
            messagebox.showinfo("Busy", "An unlock is already in progress.")
            return
        self._set_status(f"Unlocking {app_id}...")

        async def _do():
            return await unlock_app(app_id, self.cfg, self.log)

        def _done(ok):
            self._set_status("Done" if ok else f"Failed — {app_id} not found")

        self._run_async(_do(), _done)

    def _do_bulk(self):
        fp = filedialog.askopenfilename(
            title="Select AppID list file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not fp:
            return
        ids = [l.strip() for l in Path(fp).read_text().splitlines() if l.strip().isdigit()]
        if not ids:
            messagebox.showerror("Empty", "No valid AppIDs found in file.")
            return
        self.log(f"Bulk unlock: {len(ids)} AppIDs from {Path(fp).name}", "header")

        async def _do():
            ok = fail = 0
            for app_id in ids:
                if await unlock_app(app_id, self.cfg, self.log):
                    ok += 1
                else:
                    fail += 1
            return ok, fail

        def _done(result):
            ok, fail = result
            self.log(f"Bulk done: {ok} succeeded, {fail} failed.", "info")
            self._set_status(f"Bulk done: {ok}/{ok+fail}")

        self._run_async(_do(), _done)

    def _do_dump_keys(self):
        steam = get_steam_path(self.cfg)
        default = str(steam / "depotcache") if steam else ""
        dc_path = filedialog.askdirectory(
            title="Select depotcache folder",
            initialdir=default or SCRIPT_DIR,
        )
        if not dc_path:
            return
        dc = Path(dc_path)
        self.log(f"Dumping keys from: {dc}", "header")

        def _do():
            keys = dump_keys_from_depotcache(dc, self.log)
            if keys:
                out = SCRIPT_DIR / "keys.txt"
                with open(out, "w", encoding="utf-8") as f:
                    for did, k in sorted(keys.items()):
                        f.write(f'"{did}":"{k}"\n')
                self.log(f"Saved {len(keys)} keys to {out}", "ok")
            else:
                self.log("No depot keys found.", "warn")
            self._set_busy(False)

        self._set_busy(True)
        threading.Thread(target=_do, daemon=True).start()

    def _do_restart_steam(self):
        steam = get_steam_path(self.cfg)
        if not steam:
            messagebox.showerror("Not Found", "Steam path not found. Set it in Settings.")
            return
        if messagebox.askyesno("Restart Steam", "Close and restart Steam now?"):
            self.log("Restarting Steam...", "info")
            subprocess.run(["taskkill", "/F", "/IM", "steam.exe"], capture_output=True)
            time.sleep(2)
            exe = steam / "steam.exe"
            if exe.exists():
                subprocess.Popen([str(exe)])
                self.log("Steam restarted.", "ok")
            else:
                self.log("Could not find steam.exe to relaunch.", "error")

    # ── Settings dialog ───────────────────────────────────────────────────────

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("520x320")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()

        def lbl(parent, text):
            tk.Label(parent, text=text, bg=BG, fg=TEXT_DIM,
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 2))

        def entry(parent, value=""):
            e = tk.Entry(parent, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=("Segoe UI", 10), bd=0)
            e.pack(fill="x", ipady=6)
            e.insert(0, value)
            return e

        pad = tk.Frame(win, bg=BG, padx=20, pady=16)
        pad.pack(fill="both", expand=True)

        lbl(pad, "GitHub Personal Token (optional — gives 5000 req/hr instead of 60):")
        token_e = entry(pad, self.cfg.get("github_token", ""))

        lbl(pad, "Steam Install Path (leave blank to auto-detect from registry):")
        steam_e = entry(pad, self.cfg.get("steam_path", ""))

        lbl(pad, "Output Mode:")
        mode_var = tk.StringVar(value=self.cfg.get("output_mode", "auto"))
        mode_frame = tk.Frame(pad, bg=BG)
        mode_frame.pack(anchor="w", pady=(4, 0))
        tk.Radiobutton(mode_frame, text="Auto-install into Steam",
                       variable=mode_var, value="auto",
                       bg=BG, fg=TEXT, selectcolor=BG3, activebackground=BG,
                       activeforeground=TEXT).pack(side="left")
        tk.Radiobutton(mode_frame, text="Save to local folder",
                       variable=mode_var, value="local",
                       bg=BG, fg=TEXT, selectcolor=BG3, activebackground=BG,
                       activeforeground=TEXT).pack(side="left", padx=20)

        def _save():
            self.cfg["github_token"] = token_e.get().strip()
            self.cfg["steam_path"]   = steam_e.get().strip()
            self.cfg["output_mode"]  = mode_var.get()
            save_config(self.cfg)
            self._check_steam()
            self.log("Settings saved.", "ok")
            win.destroy()

        btn_row = tk.Frame(pad, bg=BG)
        btn_row.pack(fill="x", pady=(16, 0))
        ttk.Button(btn_row, text="Save", style="Accent.TButton", command=_save).pack(side="right")
        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side="right", padx=8)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    app  = SteamUnlockApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
