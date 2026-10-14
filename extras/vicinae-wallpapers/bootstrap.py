#!/usr/bin/python3
"""Fetch the verified Matugen release, build the pinned SDK bundle, and install."""
import hashlib
import io
from pathlib import Path
import platform
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent
URL = "https://github.com/InioX/matugen/releases/download/v4.2.0/matugen-4.2.0-x86_64.tar.gz"
SHA256 = "a2e3b50e49ed6439999ba3c252ed04fabd98ee4e9d12e5e5dff2e66370569751"
if platform.machine() != "x86_64":
    raise SystemExit("This setup pins the x86_64 Linux Matugen release.")
archive = urllib.request.urlopen(URL, timeout=60).read()
if hashlib.sha256(archive).hexdigest() != SHA256:
    raise SystemExit("Matugen download checksum mismatch")
with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
    member = next(item for item in bundle.getmembers() if item.isfile() and Path(item.name).name == "matugen")
    destination = ROOT / "tools/matugen"
    destination.parent.mkdir(exist_ok=True)
    destination.write_bytes(bundle.extractfile(member).read())
    destination.chmod(0o755)
subprocess.run(["npm", "ci", "--ignore-scripts"], cwd=ROOT, check=True)
subprocess.run(["npm", "run", "typecheck"], cwd=ROOT, check=True)
subprocess.run(["npm", "run", "build", "--", "--out", "dist"], cwd=ROOT, check=True)
subprocess.run(["/usr/bin/python3", "install.py"], cwd=ROOT, check=True)
subprocess.run([str(Path.home() / ".local/bin/walltheme"), "scan"], check=True)
