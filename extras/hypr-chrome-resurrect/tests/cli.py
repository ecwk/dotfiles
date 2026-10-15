#!/usr/bin/env python3
"""Isolated CLI/Unix socket smoke test. Run after `cargo build`.

Uses only Python's standard library, temp directories, and a fake hyprctl.
Never connects to or moves windows in the real Hyprland session.
"""
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import threading
import time

BINARY = Path(__file__).resolve().parents[1] / "target/debug/hypr-chrome-resurrect"
FAKE = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
path = Path(os.environ["HCR_FAKE_CLIENTS"])
context_path = path.with_suffix(".context")
data = json.loads(path.read_text())
context = json.loads(context_path.read_text()) if context_path.exists() else {"address":"0xf0","workspace":{"id":9,"name":"9"}}
args = sys.argv[1:]
def destination(value):
    return {"id":-1337,"name":value[5:]} if value.startswith("name:") else {"id":int(value),"name":value}
def find(address):
    return next((w for w in data if w["address"] == address), None)
if args == ["-j", "clients"]:
    print(json.dumps(data)); sys.exit(0)
if args == ["-j", "workspaces"]:
    print(json.dumps([w["workspace"] for w in data])); sys.exit(0)
if args == ["-j", "activewindow"]:
    print(json.dumps({"address":context["address"]})); sys.exit(0)
if args == ["-j", "activeworkspace"]:
    print(json.dumps(context["workspace"])); sys.exit(0)
if args == ["-j", "cursorpos"]:
    print(json.dumps({"x":100,"y":200})); sys.exit(0)
if args[0] != "dispatch": sys.exit(1)
command, argument = args[1:]
if command == "movetoworkspacesilent":
    value, address = argument.split(",address:")
    window = find(address)
    members = window.get("grouped",[]) or [address]
    for client in data:
        if client["address"] in members: client["workspace"] = destination(value)
elif command == "focuswindow":
    context["address"] = argument.removeprefix("address:")
    window = find(context["address"])
    if window: context["workspace"] = window["workspace"]
elif command == "workspace":
    context["workspace"] = destination(argument)
elif command == "movecursor":
    assert argument == "100 200"
elif command == "moveoutofgroup":
    address = argument.removeprefix("address:")
    for window in data:
        window["grouped"] = [a for a in window.get("grouped",[]) if a != address]
        if window["address"] == address: window["grouped"] = []
elif command == "togglegroup":
    find(context["address"])["grouped"] = [context["address"]]
elif command == "moveintogroup":
    window = find(context["address"])
    anchor = next((w for w in data if w["workspace"] == window["workspace"] and w.get("grouped") and w["address"] != window["address"]), None)
    if anchor and not window.get("grouped") and not context.get("lockgroups"):
        # Exercise head insertion; the adapter must explicitly fix tab order.
        members = [window["address"]] + anchor["grouped"]
        for member in data:
            if member["address"] in members: member["grouped"] = members[:]
elif command == "movegroupwindow":
    window = find(context["address"])
    members = window["grouped"][:]
    i = members.index(window["address"]); j = (i-1) % len(members)
    members[i], members[j] = members[j], members[i]
    for member in data:
        if member["address"] in members: member["grouped"] = members[:]
else: sys.exit(1)
temporary = path.with_suffix(".tmp")
temporary.write_text(json.dumps(data)); temporary.replace(path)
context_path.write_text(json.dumps(context))
print("ok")
'''


def wait_for(predicate, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for expected service state")


def main():
    with tempfile.TemporaryDirectory(prefix="hcr-cli-") as directory:
        root = Path(directory)
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        event_path = runtime / "hypr/fake/.socket2.sock"
        event_path.parent.mkdir(parents=True)
        event_listener = socket.socket(socket.AF_UNIX)
        event_listener.bind(str(event_path))
        event_listener.listen()
        clients = root / "clients.json"
        clients.write_text("[]")
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake = fake_bin / "hyprctl"
        fake.write_text(FAKE)
        fake.chmod(0o700)
        state = root / "state/hypr-chrome-resurrect/layout.json"
        state.parent.mkdir(parents=True)
        saved = {"version": 1, "records": [
            {"title": title, "workspace": {"kind": "numeric", "value": workspace}}
            for title, workspace in [("A", 1), ("B", 2), ("C", 10)]
        ]}
        state.write_text(json.dumps(saved))
        env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), XDG_STATE_HOME=str(root / "state"),
                   HYPRLAND_INSTANCE_SIGNATURE="fake", HCR_FAKE_CLIENTS=str(clients),
                   PATH=str(fake_bin) + os.pathsep + os.environ["PATH"])
        event_connections = []

        def accept_events():
            while True:
                try:
                    connection, _ = event_listener.accept()
                    event_connections.append(connection)
                except OSError:
                    return

        threading.Thread(target=accept_events, daemon=True).start()

        def cli(*args, ok=True):
            result = subprocess.run([str(BINARY), *args], env=env, capture_output=True, text=True, timeout=10)
            assert (result.returncode == 0) == ok, (args, result.stdout, result.stderr)
            return json.loads(result.stdout) if ok else result.stderr

        def set_clients(items):
            temporary = clients.with_suffix(".test-tmp")
            temporary.write_text(json.dumps(items))
            temporary.replace(clients)

        def chrome(address, title, workspace, window_class="google-chrome"):
            return {"address": address, "class": window_class, "title": title,
                    "workspace": {"id": workspace, "name": str(workspace)}, "mapped": True}

        log = open(root / "daemon.log", "w+")
        daemon = subprocess.Popen([str(BINARY), "daemon"], env=env, stdout=log, stderr=log)
        service_socket = runtime / "hypr-chrome-resurrect/service.sock"
        try:
            wait_for(lambda: service_socket.exists())
            assert cli("status")["phase"] == "waiting_for_chrome"
            assert "another daemon" in cli("daemon", ok=False)
            assert stat.S_IMODE(service_socket.stat().st_mode) == 0o600
            assert stat.S_IMODE(service_socket.parent.stat().st_mode) == 0o700
            wait_for(lambda: bool(event_connections))
            windows = [chrome("0xa", "A", 3), chrome("0xb", "B", 3), chrome("0xc", "C", 3),
                       chrome("0xd", "Other", 3, "Google-chrome")]
            set_clients(windows)
            event_connections[0].sendall(b"openwindow>>a,3,google-chrome,A\n")
            wait_for(lambda: [w["workspace"]["id"] for w in json.loads(clients.read_text())] == [1, 2, 10, 3])
            assert json.loads(state.read_text()) == saved
            assert cli("status")["phase"] == "restoring"

            # Dry-run is read-only, even during restoration. A manual retry moves again.
            windows = json.loads(clients.read_text())
            for window in windows[:3]:
                window["workspace"] = {"id": 3, "name": "3"}
            set_clients(windows)
            preview = cli("restore", "--dry-run")
            assert [m["to"]["value"] for m in preview["moves"]] == [1, 2, 10]
            assert json.loads(clients.read_text()) == windows
            cli("restore")
            assert [w["workspace"]["id"] for w in json.loads(clients.read_text())] == [1, 2, 10, 3]

            set_clients([chrome("0xa", "A", 2)])
            assert cli("save")["saved_records"] == 1
            assert json.loads(state.read_text())["records"][0]["workspace"]["value"] == 2
            assert json.loads(state.with_suffix(".json.bak").read_text()) == saved
            named = chrome("0xe", "Named", -1337)
            named["workspace"]["name"] = "development"
            set_clients([named])
            cli("save")
            assert json.loads(state.read_text())["records"][0]["workspace"] == {
                "kind": "named", "value": "development"}
            set_clients([chrome("0xe", "Named", 1)])
            assert cli("restore", "--dry-run")["moves"][0]["to"]["value"] == "development"
            cli("restore")
            assert json.loads(clients.read_text())[0]["workspace"]["name"] == "development"
            grouped = [chrome("0x1", "G-A", 2), chrome("0x2", "G-B", 2), chrome("0x3", "G-C", 2),
                       chrome("0x4", "G-D", 2), chrome("0x5", "G-E", 2), chrome("0xf0", "Terminal", 9, "other")]
            for window in grouped[:3]: window["grouped"] = ["0x2", "0x1", "0x3"]
            for window in grouped[3:5]: window["grouped"] = ["0x5", "0x4"]
            set_clients(grouped)
            cli("save")
            captured = json.loads(state.read_text())
            assert captured["version"] == 2
            assert captured["groups"] == [[1, 0, 2], [4, 3]]
            context = {"address":"0xf0", "workspace":{"id":9,"name":"9"}}
            clients.with_suffix(".context").write_text(json.dumps(context))
            for window in grouped[:5]:
                window["grouped"] = []
                window["workspace"] = {"id":1,"name":"1"}
            set_clients(grouped)
            assert cli("restore", "--dry-run")["groups"] == [["0x2","0x1","0x3"],["0x5","0x4"]]
            assert json.loads(clients.read_text()) == grouped
            restored = cli("restore")
            assert not restored["failed_moves"], restored
            actual = json.loads(clients.read_text())
            for window in actual[:3]: assert window["grouped"] == ["0x2","0x1","0x3"]
            for window in actual[3:5]: assert window["grouped"] == ["0x5","0x4"]
            assert [w["workspace"]["id"] for w in actual] == [2,2,2,2,2,9]
            assert json.loads(clients.with_suffix(".context").read_text()) == context
            assert json.loads(state.read_text()) == captured
            # A group lock must report failure, preserve state, and return all
            # windows from staging even after a partially created group.
            for window in grouped[:5]:
                window["grouped"] = []
                window["workspace"] = {"id":1,"name":"1"}
            set_clients(grouped)
            locked_context = dict(context, lockgroups=True)
            clients.with_suffix(".context").write_text(json.dumps(locked_context))
            failed = cli("restore")
            assert len(failed["failed_moves"]) == 2, failed
            assert all(w["workspace"]["name"] == "2" for w in json.loads(clients.read_text())[:5])
            assert json.loads(clients.with_suffix(".context").read_text()) == locked_context
            assert json.loads(state.read_text()) == captured
            clients.with_suffix(".context").write_text(json.dumps(context))
            assert not cli("restore")["failed_moves"]
            before = state.read_bytes()
            set_clients([])
            assert "empty" in cli("save", ok=False)
            assert state.read_bytes() == before
            assert stat.S_IMODE(state.stat().st_mode) == 0o600

            # Invalid requests get an error response rather than stopping the service.
            with socket.socket(socket.AF_UNIX) as connection:
                connection.connect(str(service_socket))
                connection.sendall(b"not-json\n")
                connection.settimeout(5)
                with connection.makefile("r") as response:
                    assert json.loads(response.readline())["ok"] is False
            assert cli("status")["service"] == "running"

            daemon.terminate()
            daemon.wait(timeout=5)
            assert cli("status")["service"] == "unavailable"
            # A stale socket left by process termination is safely replaced.
            daemon = subprocess.Popen([str(BINARY), "daemon"], env=env, stdout=log, stderr=log)
            wait_for(lambda: cli("status")["service"] == "running")
            daemon.terminate()
            daemon.wait(timeout=5)
            state.write_text("malformed")
            assert "malformed state" in cli("daemon", ok=False)
            assert state.read_text() == "malformed"
            print("CLI smoke test passed: IPC, restoration, dry-run, save, permissions, locking, stale socket, malformed state")
        finally:
            if daemon.poll() is None:
                daemon.terminate()
                daemon.wait(timeout=5)
            for connection in event_connections:
                connection.close()
            event_listener.close()
            log.close()


if __name__ == "__main__":
    main()
