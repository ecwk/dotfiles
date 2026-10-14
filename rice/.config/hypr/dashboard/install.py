#!/usr/bin/python
"""Install symlinks only; refuse to replace unrelated files."""
import os
from pathlib import Path
import subprocess
import sys
from core import ROOT,STATE,write_json,read_json
HOME=Path.home()
LINKS={
    HOME/'.local/bin/glass-dashboard':ROOT/'launch',
    HOME/'.config/systemd/user/glass-dashboard.service':ROOT/'integration/glass-dashboard.service',
    HOME/'.local/share/applications/io.github.ecwk.GlassDashboard.desktop':ROOT/'integration/io.github.ecwk.GlassDashboard.desktop',
}
MAIN=HOME/'.config/hypr/hyprland.conf'
SOURCE_PATH=str(ROOT/'integration/hyprland.conf')
if SOURCE_PATH.startswith(str(HOME)+'/'): SOURCE_PATH='~/'+SOURCE_PATH[len(str(HOME))+1:]
HOOK=f'source = {SOURCE_PATH}'

def run(*args): subprocess.run(args,check=True)

def install():
    for dest,source in LINKS.items():
        if (dest.exists() or dest.is_symlink()) and (not dest.is_symlink() or dest.resolve()!=source.resolve()):
            raise SystemExit(f'Refusing to overwrite existing file: {dest}')
    if not MAIN.exists(): raise SystemExit('Hyprland config not found: '+str(MAIN))
    if (MAIN.parent/'hyprland.lua').exists(): raise SystemExit('Lua config detected; review integration before installing')
    version=subprocess.check_output(['hyprctl','version'],text=True)
    if '0.56.' not in version: raise SystemExit('This integration was verified on Hyprland 0.56; review rules for this version first')
    existing=MAIN.read_text()
    STATE.mkdir(parents=True,exist_ok=True)
    for dest,source in LINKS.items():
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.is_symlink(): dest.symlink_to(source)
    if HOOK not in existing.splitlines():
        backup=STATE/'hyprland.conf.before-dashboard'
        if not backup.exists(): backup.write_text(existing)
        MAIN.write_text(existing.rstrip()+'\n\n'+HOOK+'\n')
    write_json(STATE/'installation.json',{'root':str(ROOT),'hook':HOOK,'links':{str(k):str(v) for k,v in LINKS.items()}})
    run('hyprctl','reload')
    errors=subprocess.check_output(['hyprctl','configerrors'],text=True).strip()
    if errors:
        MAIN.write_text(existing)
        run('hyprctl','reload')
        raise SystemExit('Hyprland reported errors; include rolled back:\n'+errors)
    run('systemctl','--user','daemon-reload')
    run('systemctl','--user','enable','--now','glass-dashboard.service')
    print('Installed via symlinks. Source:',ROOT)

def uninstall():
    subprocess.run(['systemctl','--user','disable','--now','glass-dashboard.service'],check=False)
    record=read_json(STATE/'installation.json',{})
    hook=record.get('hook',HOOK)
    if MAIN.exists():
        MAIN.write_text('\n'.join(line for line in MAIN.read_text().splitlines() if line!=hook)+'\n')
    for dest,source in LINKS.items():
        if dest.is_symlink() and dest.resolve()==source.resolve(): dest.unlink()
    run('systemctl','--user','daemon-reload')
    subprocess.run(['hyprctl','reload'],check=False)
    print('Removed dashboard integration. Source and personal state preserved.')

if __name__=='__main__':
    uninstall() if '--uninstall' in sys.argv else install()
