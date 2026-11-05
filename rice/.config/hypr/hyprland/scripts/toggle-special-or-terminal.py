#!/usr/bin/python3
"""Hide the focused monitor's special workspace, or show the terminal one."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    # Serialize rapid key presses so each reads the previous press's result.
    session = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
    lock_path = Path(os.environ["XDG_RUNTIME_DIR"]) / ("hypr-special-toggle-" + session + ".lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        monitors = json.loads(subprocess.check_output(
            ["hyprctl", "-j", "monitors"], text=True, timeout=5,
        ))
        monitor = next(m for m in monitors if m["focused"])
        special = monitor["specialWorkspace"]
        target = special["name"].removeprefix("special:") if special["id"] else "magic"
        if special["id"] and special["name"] == "special":
            target = ""
        result = subprocess.run(
            ["hyprctl", "dispatch", "togglespecialworkspace", target],
            capture_output=True, text=True, check=True, timeout=5,
        )
        if result.stdout.strip() != "ok":
            raise RuntimeError(result.stdout.strip() or result.stderr.strip())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Toggle special workspace: {error}", file=sys.stderr)
        sys.exit(1)
