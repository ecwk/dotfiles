#!/usr/bin/python3
"""Toggle desktop view without moving or rearranging application windows.

Hyprland 0.56.2 legacy dispatchers:
https://github.com/hyprwm/Hyprland/blob/v0.56.2/src/config/legacy/DispatcherTranslator.cpp
"""
import fcntl
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import time


def query(command, *arguments):
    return json.loads(subprocess.check_output(["hyprctl", "-j", command, *arguments], text=True, timeout=5))


def control(*arguments):
    result = subprocess.run(
        ["hyprctl", *arguments],
        capture_output=True, text=True, check=True, timeout=5,
    )
    if result.stdout.strip() != "ok":
        raise RuntimeError(result.stdout.strip() or result.stderr.strip())


def dispatch(command, argument):
    control("dispatch", command, str(argument))


def recover_animations(marker):
    if marker.exists():
        enabled = int(marker.read_text())
        control("keyword", "animations:enabled", str(enabled))
        marker.unlink()


@contextmanager
def without_animations(marker):
    recover_animations(marker)
    enabled = query("getoption", "animations:enabled")["int"]
    if not enabled:
        yield
        return
    marker.write_text(str(enabled))
    try:
        # The child waits for our lock to release. It restores the saved setting
        # if this process is killed before finally runs, including SIGKILL.
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--recover-animations"],
            start_new_session=True, close_fds=True,
        )
        control("keyword", "animations:enabled", "0")
        yield
    finally:
        # Hyprland 0.56.2 snaps disabled animations on its next animation tick.
        # Let that tick run before enabling animations again.
        time.sleep(0.03)
        recover_animations(marker)


def interrupted(signum, frame):
    raise InterruptedError(f"Interrupted by signal {signum}")


def workspace_arg(workspace):
    return str(workspace["id"]) if workspace["id"] > 0 else "name:" + workspace["name"]


def same_window(saved, current):
    return current and all(saved.get(k) == current.get(k) for k in ("address", "pid", "stableId"))


def restore(state):
    monitors = {m["name"]: m for m in query("monitors")}
    for saved in state["monitors"]:
        if saved["name"] not in monitors:
            continue
        dispatch("focusmonitor", saved["name"])
        current = next(m for m in query("monitors") if m["name"] == saved["name"])
        if current["specialWorkspace"]["id"]:
            dispatch("togglespecialworkspace", current["specialWorkspace"]["name"].removeprefix("special:"))
        if current["activeWorkspace"]["id"] != saved["activeWorkspace"]["id"]:
            dispatch("workspace", workspace_arg(saved["activeWorkspace"]))
        special = saved["specialWorkspace"]
        if special["id"] and any(w["id"] == special["id"] for w in query("workspaces")):
            dispatch("togglespecialworkspace", special["name"].removeprefix("special:"))
    clients = {c["address"]: c for c in query("clients")}
    for saved in state["pinned"]:
        current = clients.get(saved["address"])
        if same_window(saved, current) and not current["pinned"]:
            dispatch("pin", "address:" + saved["address"])
    focused = next((m for m in state["monitors"] if m["focused"]), None)
    if focused and focused["name"] in monitors:
        dispatch("focusmonitor", focused["name"])
    saved = state["activewindow"]
    current = clients.get(saved.get("address"))
    if same_window(saved, current) and current["workspace"]["id"] == saved["workspace"]["id"]:
        dispatch("focuswindow", "address:" + saved["address"])


def toggle(state_path):
    if state_path.exists():
        restore(json.loads(state_path.read_text()))
        state_path.unlink()
        return
    state = {
        "monitors": query("monitors"),
        "activewindow": query("activewindow"),
        "pinned": [c for c in query("clients") if c["pinned"]],
    }
    # Save before dispatching so interruption or partial failure remains recoverable.
    state_path.write_text(json.dumps(state))
    try:
        for client in state["pinned"]:
            dispatch("pin", "address:" + client["address"])
        used_names = {workspace["name"] for workspace in query("workspaces")}
        for monitor in state["monitors"]:
            dispatch("focusmonitor", monitor["name"])
            special = monitor["specialWorkspace"]
            if special["id"]:
                dispatch("togglespecialworkspace", special["name"].removeprefix("special:"))
            # Use a readable Waybar label, and never select an existing workspace
            # that might contain windows opened during an earlier desktop view.
            name, suffix = "🌌", 1
            while name in used_names:
                suffix += 1
                name = f"🌌 {suffix}"
            used_names.add(name)
            dispatch("workspace", "name:" + name)
        focused = next((m for m in state["monitors"] if m["focused"]), None)
        if focused:
            dispatch("focusmonitor", focused["name"])
    except Exception:
        restore(state)
        state_path.unlink()
        raise


def main():
    # Isolate state per compositor session; flock prevents rapid presses racing.
    session = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    state_path = runtime / ("hypr-show-desktop-" + session + ".json")
    lock_path = state_path.with_suffix(".lock")
    marker = state_path.with_suffix(".animations")
    recovering = sys.argv[1:] == ["--recover-animations"]
    if not recovering:
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(signum, interrupted)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if recovering:
            # Keep the marker on failure so a later Super+D can recover too.
            for attempt in range(3):
                try:
                    recover_animations(marker)
                    return
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(0.1)
        else:
            with without_animations(marker):
                toggle(state_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Show desktop: {error}", file=sys.stderr)
        sys.exit(1)
