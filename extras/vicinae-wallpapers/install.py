#!/usr/bin/env python3
"""Install built extension, palette CLI, and login restoration."""
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess

source = Path(__file__).resolve().parent
home = Path.home()
data = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
state = Path(os.environ.get('XDG_STATE_HOME', home / '.local/state'))
backup = state / 'walltheme/backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
library = data / 'walltheme/lib'
extension = data / 'vicinae/extensions/walltheme'
autostart = home / '.config/hypr/hyprland/autostart.conf'
old = data / 'vicinae/scripts/select-wallpaper.py'
assert (source / 'dist/select-wallpaper.js').is_file(), 'Build the extension first'
assert (source / 'tools/matugen').is_file(), 'Matugen 4.2.0 must be present in tools/'
backup.mkdir(parents=True)
for name, target in [('lib', library), ('extension', extension)]:
    if target.exists(): shutil.copytree(target, backup / name)
shutil.copy2(autostart, backup / 'autostart.conf')
if old.exists(): shutil.copy2(old, backup / 'select-wallpaper.py')
library.mkdir(parents=True, exist_ok=True)
(library / 'tools').mkdir(exist_ok=True)
shutil.copy2(source / 'walltheme.py', library / 'walltheme.py')
shutil.copy2(source / 'tools/matugen', library / 'tools/matugen')
(library / 'walltheme.py').chmod(0o755)
(library / 'tools/matugen').chmod(0o755)
shutil.copytree(source / 'dist', extension, dirs_exist_ok=True)
binary = home / '.local/bin/walltheme'
binary.parent.mkdir(parents=True, exist_ok=True)
if binary.is_symlink() or binary.exists(): binary.unlink()
binary.symlink_to(library / 'walltheme.py')
old_entry = 'exec-once = uwsm app -- ~/.local/share/vicinae/scripts/select-wallpaper.py --restore'
entry = 'exec-once = uwsm app -- ~/.local/bin/walltheme restore'
content = autostart.read_text().replace(old_entry, entry)
if entry not in content.splitlines(): content = content.rstrip() + '\n' + entry + '\n'
autostart.write_text(content)
old.unlink(missing_ok=True)
subprocess.run([str(binary), 'initialize'], check=True, stdout=subprocess.DEVNULL)
print(f'Installed CLI: {binary}\nInstalled extension: {extension}\nBackup: {backup}')
