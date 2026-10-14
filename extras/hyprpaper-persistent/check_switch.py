import subprocess,json,time,threading,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rice/.local/share/walltheme/lib'))
import walltheme as w
original=w.active(); choices=[e['path'] for e in w.collection()['entries'] if e['path'] not in original.values()]
values=[]; addresses=set()
try:
    worker=threading.Thread(target=w.apply_all,args=(choices[0],));worker.start()
    until=time.monotonic()+.8
    while time.monotonic()<until:
        layers=json.loads(subprocess.check_output(['hyprctl','layers','-j']))
        addresses.update(s['address'] for m in layers.values() for ls in m['levels'].values() for s in ls if s['namespace']=='hyprpaper')
        values.append([s['alpha'] for m in layers.values() for ls in m['levels'].values() for s in ls if s['namespace']=='hyprpaper'])
    worker.join()
finally:
    for monitor,path in original.items():w.set_wallpaper(path,monitor)
print('samples:',len(values),'translucent:',sum(any(a<.999 for a in row) for row in values),'empty:',sum(not row for row in values),'minimum:',min((a for row in values for a in row),default=None))
print('first samples:',values[:12])

assert values and all(row and all(a==1 for a in row) for row in values), 'Wallpaper became transparent or disappeared'
assert len(addresses)==len(original), 'Wallpaper surface was recreated'
print('PASS: mapped wallpaper surfaces remained opaque and stable')
