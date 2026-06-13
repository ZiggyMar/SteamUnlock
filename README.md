# SteamUnlock

A free, open-source Steam manifest tool — a community-built alternative to SteamTools.

---

## Why this exists

I was fed up with the official SteamTools. It's a closed-source Chinese app that runs a kernel driver 24/7, triggers every antivirus on the planet, and nobody can actually audit what it does. It felt like a virus on my PC, and there's a very real risk of getting banned if Valve ever decides to crack down on it.

So I combined a handful of open-source projects that solve pieces of this problem — manifest downloaders, key dumpers, Lua script generators — into one clean, auditable tool. Every line of code is right here. No drivers, no hidden services, no mystery.

**You can do anything you want with this project except sell it.**

---

## How it works

Steam verifies game files against **depot manifests** — small metadata files that describe which files belong to which version of a game. The community uploads these manifests to public GitHub repositories after legitimately owning and playing a game. SteamUnlock fetches those manifests and installs them into Steam's own directories, along with a small Lua script that tells SteamTools' lightweight shim (the only closed-source piece left) which depots to load.

### The full pipeline

1. **Search** — query the Steam store API for game name → AppID
2. **Discover** — check 7 known community manifest repos in parallel, plus a live GitHub search for any *new* repos that have the game's manifests (this is how brand-new uploads get found automatically)
3. **Select** — pick the repo with the most recent commit date for that AppID branch
4. **Download** — pull the `.manifest` files via CDN mirrors (jsDelivr, jsdmirror, etc.) with automatic fallback
5. **Install** — write manifests to `Steam/depotcache/` and generate a `{appid}.lua` into `Steam/config/stplug-in/`
6. **Restart Steam** — the shim picks everything up on next launch

---

## Why it's better than SteamTools

| | SteamTools | SteamUnlock |
|---|---|---|
| Source code | ❌ Closed source | ✅ 100% open |
| Kernel driver | ❌ Installs one | ✅ None |
| Background service | ❌ Runs 24/7 | ✅ None — exits when you close it |
| Antivirus flags | ❌ Constant false positives | ✅ Clean |
| Ban risk | ❌ Kernel-level hooks | ✅ Standard file writes only |
| GitHub manifest search | 5 repos | ✅ 7+ repos + live search |
| Token support | ❌ No | ✅ .env or in-app settings |
| Standalone exe | ❌ Requires installer | ✅ Single file, no install |

---

## Does it auto-update for new games?

**Yes, for game coverage** — the community repos (ManifestAutoUpdate, ManifestHub, etc.) automatically receive new manifests when community members upload them. Every time you unlock a game SteamUnlock fetches the latest state of those repos, so coverage improves over time with zero action on your part.

**For very new or obscure games** — if a game isn't in any repo yet, SteamUnlock uses the GitHub code search API to scan *all* public repos for manifest files matching the AppID. This means even repos we've never heard of will be checked. You need a GitHub token for this to work reliably (see below).

---

## Setup

### Standalone exe (easiest)

Download `SteamUnlock.exe` from [Releases](../../releases) and double-click. No installer, no Python, no dependencies.

### Running from source

```bash
# 1. Clone
git clone https://github.com/yourname/SteamUnlock
cd SteamUnlock

# 2. Install dependencies
pip install aiohttp pillow

# 3. Launch the GUI overlay
pythonw SteamUnlock/SteamUnlock_GUI.pyw

# Or the CLI
python SteamUnlock/steamunlock.py
```

### GitHub API token (strongly recommended)

Without a token you're capped at **60 API requests/hour** and searches will silently fail mid-way. A free token gives **5000/hour** and also enables the live repo discovery search for obscure games.

**Get a token:** GitHub → Settings → Developer settings → Personal access tokens → Generate new token (classic) → tick **public_repo** → copy it.

**Option A — .env file** (recommended, keeps it out of `config.json`):
```
# SteamUnlock/.env
GITHUB_TOKEN=ghp_yourtoken
```

**Option B — in-app Settings panel:**
Right-click the floating icon → Settings → paste your token → optionally tick "Save to .env".

**Option C — config.json** (auto-generated on first run):
```json
{ "github_token": "ghp_yourtoken" }
```

---

## Building the exe yourself

```bash
pip install pyinstaller
cd SteamUnlock
build_exe.bat
```

Output: `SteamUnlock/dist/SteamUnlock.exe` — single file, fully standalone.

---

## Libraries and tools used

- **Python 3** — core language
- **aiohttp** — async HTTP for parallel manifest fetching and GitHub API calls
- **tkinter** — GUI (ships with Python, no extra install)
- **Pillow / cairosvg** — used at build time to rasterize icons extracted from the SteamTools binary
- **PyInstaller** — packages everything into the standalone exe
- Community manifest repos: SteamAutoCracks/ManifestHub, ikun0014/ManifestHub, Auiowu/ManifestAutoUpdate, tymolu233/ManifestAutoUpdate-fix, wxy1343/ManifestAutoUpdate, Fairyvmos/bruh-hub, hansaes/ManifestAutoUpdate

---

## License

**CC BY-NC 4.0** — free to use, modify, and share. **You cannot sell this.**

See [LICENSE](LICENSE) for the full text.
