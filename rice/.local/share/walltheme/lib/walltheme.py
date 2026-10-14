#!/usr/bin/python3
"""Wallpaper palettes and a transactional Hyprpaper preview session. Python stdlib only."""
import argparse
import asyncio
import base64
import configparser
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

HOME = Path.home()
ROOT = Path(__file__).resolve().parent
def xdg(name, default):
    value = os.environ.get(name, "")
    return Path(value) if value.startswith("/") else HOME / default
DATA = xdg("XDG_DATA_HOME", ".local/share") / "walltheme"
STATE = xdg("XDG_STATE_HOME", ".local/state") / "walltheme"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "walltheme"
CONFIG = HOME / ".config/waypaper/config.ini"
WAYPAPER = HOME / ".local/bin/waypaper"
MATUGEN = ROOT / "tools/matugen"
ROLES = dict(background="surface", surface="surface_container", foreground="on_surface",
             muted="on_surface_variant", border="outline_variant", accent="primary", on_accent="on_primary")
RECIPE = {"name": "matugen", "version": "4.2.0", "scheme": "scheme-tonal-spot", "sourceColorIndex": 0, "contrast": 0}
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".jxl"}

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".walltheme-")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

@contextlib.contextmanager
def lock(path, blocking=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield

def read_json(path, default=None):
    try: return json.loads(path.read_text())
    except FileNotFoundError: return default

def run(args, timeout=30):
    result = subprocess.run([str(a) for a in args], text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"Command failed: {args[0]}")
    return result.stdout

def settings():
    cfg = configparser.ConfigParser(interpolation=None)
    if not cfg.read(CONFIG): raise RuntimeError(f"Missing Waypaper configuration: {CONFIG}")
    return cfg

def folders():
    return [Path(os.path.expandvars(p.strip())).expanduser().resolve()
            for p in settings().get("Settings", "folder").splitlines() if p.strip()]

def extract(image):
    path = Path(image).expanduser().resolve(strict=True)
    with path.open("rb") as stream: digest = hashlib.file_digest(stream, "sha256").hexdigest()
    key = hashlib.sha256((digest + json.dumps(RECIPE, sort_keys=True)).encode()).hexdigest()
    target = DATA / "palettes" / f"{key}.json"
    with lock(DATA / "palette.lock"):
        record = read_json(target)
        if record is None:
            # An isolated config prevents the user's Matugen settings affecting the recipe.
            config = DATA / "matugen.toml"
            atomic(config, b"[config]\n[templates]\n")
            raw = json.loads(run([MATUGEN, "image", path, "--config", config, "--dry-run",
                                  "--source-color-index", "0", "--type", RECIPE["scheme"],
                                  "--contrast", "0", "--json", "hex"], timeout=60))
            palettes = {mode: {role: raw["colors"][source][mode]["color"].upper()
                               for role, source in ROLES.items()} for mode in ("dark", "light")}
            if any(not re.fullmatch(r"#[0-9A-F]{6}", c) for p in palettes.values() for c in p.values()):
                raise RuntimeError("Matugen returned an invalid palette")
            record = {"schemaVersion": 1, "id": key, "sha256": digest,
                      "generator": RECIPE, "palettes": palettes}
        if "swatches" not in record:
            record["swatches"] = {}
            for mode, colors in record["palettes"].items():
                record["swatches"][mode] = {}
                for role, color in colors.items():
                    swatch = DATA / "swatches" / f"{color[1:]}.svg"
                    if not swatch.exists():
                        atomic(swatch, (f'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect x="2" y="2" width="28" height="28" rx="5" fill="{color}" stroke="#888888" stroke-width="2"/></svg>').encode())
                    record["swatches"][mode][role] = str(swatch)
            atomic(target, record)
        index = read_json(DATA / "index.json", {})
        stat = path.stat()
        index[str(path)] = {"id": key, "mtimeNs": stat.st_mtime_ns, "size": stat.st_size}
        atomic(DATA / "index.json", index)
    return {**record, "wallpaper": str(path)}

def publish(image, mode="dark"):
    record = extract(image)
    record.update(mode=mode, colors=record["palettes"][mode])
    atomic(STATE / "current.json", record)
    return record

def active():
    text = run(["hyprctl", "hyprpaper", "listactive"], 5)
    if "error:" in text.lower(): raise RuntimeError(text.strip())
    return dict(line.split(": ", 1) for line in text.splitlines() if ": " in line)

def monitors():
    return json.loads(run(["hyprctl", "monitors", "-j"], 5))

def collection():
    paths = {str(p.resolve()) for root in folders() if root.is_dir()
             for p in root.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS}
    try:
        current, displays = active(), monitors()
    except (RuntimeError, OSError, subprocess.SubprocessError):
        current, displays = {}, []
    paths.update(p for p in current.values() if Path(p).is_file())
    index = read_json(DATA / "index.json", {})
    entries = []
    for path in sorted(paths, key=str.casefold):
        p = Path(path)
        cached = index.get(path, {})
        stat = p.stat()
        palette = None
        if cached.get("mtimeNs") == stat.st_mtime_ns and cached.get("size") == stat.st_size:
            palette = read_json(DATA / "palettes" / f"{cached.get('id')}.json")
            if palette and palette.get("generator") != RECIPE: palette = None
        entries.append({"path": path, "name": p.name, "activeOn": [m for m, value in current.items() if value == path],
                        "palette": palette})
    focused = next((m["name"] for m in displays if m.get("focused")), next(iter(current), None))
    return {"entries": entries, "active": current, "selected": current.get(focused),
            "mode": read_json(STATE / "current.json", {}).get("mode", "dark"), "folder": str(folders()[0])}

def scan():
    result = {"generated": 0, "errors": []}
    for entry in collection()["entries"]:
        try:
            extract(entry["path"])
            result["generated"] += 1
        except Exception as error: result["errors"].append({"path": entry["path"], "error": str(error)})
    return result

def set_wallpaper(image, monitor):
    path = Path(image).expanduser().resolve(strict=True)
    if any(c in str(path) for c in (",", "\n", "\r")):
        raise RuntimeError("Hyprpaper cannot accept commas or newlines in wallpaper paths")
    response = run(["hyprctl", "hyprpaper", "wallpaper", f"{monitor},{path}"], 10)
    if "error" in response.lower(): raise RuntimeError(response.strip())

def apply_all(image):
    names = [m["name"] for m in monitors()]
    if not names: raise RuntimeError("No active monitors")
    for name in names: set_wallpaper(image, name)
    for _ in range(15):
        actual = active()
        if all(actual.get(m) == str(Path(image).resolve()) for m in names): return
        time.sleep(.1)
    raise RuntimeError("Hyprpaper did not confirm the wallpaper on all monitors")

def saved_files():
    cfg = settings()
    files = [CONFIG, STATE / "current.json"]
    if cfg.getboolean("Settings", "use_xdg_state", fallback=False):
        raise RuntimeError("This integration currently requires Waypaper use_xdg_state = False")
    return {str(p): base64.b64encode(p.read_bytes()).decode() if p.exists() else None for p in files}

def restore_snapshot(snapshot, files=False):
    connected = {m["name"] for m in monitors()}
    errors = []
    for monitor, image in snapshot["active"].items():
        if monitor in connected:
            try: set_wallpaper(image, monitor)
            except Exception as error: errors.append(str(error))
    if errors: raise RuntimeError("; ".join(errors))
    if files:
        for name, data in snapshot["files"].items():
            if data is None: Path(name).unlink(missing_ok=True)
            else: atomic(Path(name), base64.b64decode(data))

def session_paths():
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if not signature: raise RuntimeError("A running Hyprland session is required")
    key = hashlib.sha256(signature.encode()).hexdigest()[:16]
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    return RUNTIME / f"{key}.sock", RUNTIME / f"{key}.lock", STATE / f"recovery-{key}.json"

def recover(journal):
    previous = read_json(journal)
    if previous:
        restore_snapshot(previous, files=previous.get("committing", False))
        journal.unlink()

class Session:
    def __init__(self, token, journal):
        self.token, self.journal = token, journal
        recover(journal)
        self.snapshot = {"active": active(), "files": saved_files(), "committing": False}
        if not self.snapshot["active"]: raise RuntimeError("No active wallpaper to restore")
        self.mutex = asyncio.Lock()
        self.last_beat = time.monotonic()
        self.generation = 0
        self.closed = False
        self.done = asyncio.Event()
        self.seen_open = subprocess.run(["vicinae", "state", "open"], capture_output=True, timeout=3).returncode == 0

    async def cancel(self):
        self.closed = True
        self.generation += 1
        async with self.mutex:
            if self.journal.exists():
                await asyncio.to_thread(restore_snapshot, self.snapshot, self.snapshot["committing"])
                self.journal.unlink()
            self.done.set()

    async def request(self, data):
        if data.get("token") != self.token: raise RuntimeError("Another wallpaper picker is already open")
        op = data["op"]
        if op == "cancel":
            await self.cancel()
            return {}
        if self.closed: raise RuntimeError("Preview session has ended; reopen the command")
        if op == "heartbeat":
            self.last_beat = time.monotonic()
            return {}
        if op == "status": return self.snapshot["active"]
        if op not in ("preview", "commit"): raise RuntimeError("Unknown session operation")
        self.generation += 1
        generation = self.generation
        async with self.mutex:
            if generation != self.generation or self.closed: return {"skipped": True}
            image = str(Path(data["image"]).resolve(strict=True))
            if op == "preview":
                atomic(self.journal, self.snapshot)
                await asyncio.to_thread(apply_all, image)
                return {"image": image}
            mode = data.get("mode", "dark")
            if mode not in ("dark", "light"): raise RuntimeError("Invalid palette mode")
            await asyncio.to_thread(extract, image)
            self.snapshot["committing"] = True
            atomic(self.journal, self.snapshot)
            try:
                await asyncio.to_thread(run, [WAYPAPER, "--wallpaper", image])
                await asyncio.to_thread(apply_all, image)
                theme = await asyncio.to_thread(publish, image, mode)
                self.snapshot = {"active": active(), "files": saved_files(), "committing": False}
                self.journal.unlink(missing_ok=True)
                return {"active": self.snapshot["active"], "theme": theme}
            except Exception:
                await asyncio.to_thread(restore_snapshot, self.snapshot, True)
                self.snapshot["committing"] = False
                self.journal.unlink(missing_ok=True)
                raise

    async def connection(self, reader, writer):
        try:
            data = json.loads(await asyncio.wait_for(reader.readline(), 5))
            value = await self.request(data)
            reply = {"ok": True, "value": value}
        except Exception as error: reply = {"ok": False, "error": str(error)}
        writer.write((json.dumps(reply) + "\n").encode())
        with contextlib.suppress(ConnectionError): await writer.drain()
        writer.close()

    async def watch(self):
        while not self.done.is_set():
            await asyncio.sleep(.3)
            try:
                result = await asyncio.to_thread(subprocess.run, ["vicinae", "state", "open"],
                                                  capture_output=True, timeout=3)
                opened = result.returncode == 0
                self.seen_open |= opened
                if (self.seen_open and not opened) or time.monotonic() - self.last_beat > 3:
                    await self.cancel()
            except Exception as error:
                print(f"Preview recovery: {error}", file=sys.stderr)
                # Keep recovery journal and retry; never silently discard a failed rollback.

async def serve(token):
    sock, lockfile, journal = session_paths()
    with lock(lockfile, blocking=False):
        session = Session(token, journal)
        sock.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(session.connection, path=str(sock), limit=65536)
        os.chmod(sock, 0o600)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(session.cancel()))
        watcher = asyncio.create_task(session.watch())
        try:
            async with server: await session.done.wait()
        finally:
            watcher.cancel()
            sock.unlink(missing_ok=True)

def login_restore():
    deadline = time.monotonic() + 30
    while True:
        try: active(); break
        except Exception:
            if time.monotonic() > deadline: raise RuntimeError("Hyprpaper did not start")
            time.sleep(.5)
    _, lockfile, journal = session_paths()
    with lock(lockfile, blocking=False): recover(journal)
    run([WAYPAPER, "--restore"])
    if not (STATE / "current.json").exists():
        image = settings().get("Settings", "wallpaper").splitlines()[0]
        publish(image)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("extract"); p.add_argument("image")
    for name in ("scan", "list", "restore", "initialize"): sub.add_parser(name)
    p = sub.add_parser("get"); p.add_argument("role", choices=ROLES); p.add_argument("--image"); p.add_argument("--mode", choices=("dark", "light"))
    p = sub.add_parser("export"); p.add_argument("--format", choices=("json", "shell"), default="json"); p.add_argument("--mode", choices=("dark", "light"))
    p = sub.add_parser("serve"); p.add_argument("token")
    sub.add_parser("socket")
    args = parser.parse_args()
    if args.command == "extract": result = extract(args.image)
    elif args.command == "scan": result = scan()
    elif args.command == "list": result = collection()
    elif args.command == "initialize":
        result = read_json(STATE / "current.json") or publish(settings().get("Settings", "wallpaper").splitlines()[0])
    elif args.command == "restore": login_restore(); return
    elif args.command == "serve": asyncio.run(serve(args.token)); return
    elif args.command == "socket": print(session_paths()[0]); return
    else:
        record = extract(args.image) if getattr(args, "image", None) else read_json(STATE / "current.json")
        if record is None: raise RuntimeError("No committed theme; run walltheme initialize")
        mode = args.mode or record.get("mode", "dark")
        colors = record["palettes"][mode]
        if args.command == "get": print(colors[args.role]); return
        if args.format == "shell":
            for key in ROLES:
                if not re.fullmatch(r"#[0-9A-Fa-f]{6}", colors[key]): raise RuntimeError("Invalid theme color")
                print(f"export WALLTHEME_{key.upper()}='{colors[key]}'")
            return
        result = {**record, "mode": mode, "colors": colors}
    print(json.dumps(result))

if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(f"walltheme: {error}", file=sys.stderr)
        sys.exit(1)
