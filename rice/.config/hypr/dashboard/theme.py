"""Walltheme's public semantic palette; no wallpaper-specific colors are stored here."""
import json
import os
import re
from pathlib import Path

MODES = ('full', 'accents', 'original')
ROLES = ('background', 'surface', 'foreground', 'muted', 'border', 'accent', 'on_accent')
THEME_FILE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'walltheme/current.json'

def read_palette(path=THEME_FILE):
    try:
        data=json.loads(path.read_text()); colors=data['colors']
        if not all(isinstance(colors.get(k),str) and re.fullmatch(r'#[0-9a-fA-F]{6}',colors[k]) for k in ROLES):
            return None
        return {k:colors[k] for k in ROLES}
    except (OSError,ValueError,KeyError,TypeError,AttributeError): return None

def rgba(hexcolor, alpha):
    return 'rgba(%s,%s)' % (','.join(str(int(hexcolor[i:i+2],16)) for i in (1,3,5)),alpha)

def mix(a,b,t):
    return '#'+''.join(f'{round(int(a[i:i+2],16)*(1-t)+int(b[i:i+2],16)*t):02x}' for i in (1,3,5))

def css(mode,c):
    if mode=='original' or not c: return ''
    a=c['accent']; on=c['on_accent']
    result=f'''
.accent, *:link, *:visited {{ color: {a}; }}
progressbar progress, scale highlight {{ background: {a}; }}
button.primary, check:checked {{ background: {a}; color: {on}; }}
button:focus-visible, entry:focus-visible {{ outline-color: {a}; border-color: {rgba(a,.5)}; }}
'''
    if mode=='accents': return result
    bg,surf,fg,muted,border=(c[k] for k in ROLES[:5])
    return result+f'''
window {{ color: {fg}; }}
.glass {{ background: linear-gradient(140deg, {rgba(surf,.70)}, {rgba(bg,.57)}); border-color: {rgba(border,.24)}; }}
.heading, .subtitle {{ color: {muted}; }}
button {{ background: {rgba(fg,.08)}; color: {fg}; border-color: {rgba(border,.3)}; }}
button:hover {{ background: {rgba(a,.19)}; }}
button.primary {{ background: {a}; color: {on}; }}
button.flat {{ background: transparent; border: none; }}
entry {{ background: {rgba(bg,.3)}; color: {fg}; border-color: {rgba(border,.35)}; }}
progressbar trough, scale trough {{ background: {rgba(muted,.15)}; }}
.art {{ background: {rgba(muted,.1)}; }}
.error {{ color: {a}; }}
popover contents {{ background: {surf}; color: {fg}; border-color: {border}; }}
textview, textview text {{ color: {fg}; }}
.dock {{ background: {rgba(bg,.65)}; }}
/* Keep Default btop readable even when the committed wallpaper mode is light. */
.btop-original {{ background: linear-gradient(140deg, rgba(16,16,16,.70), rgba(4,4,4,.57)); }}
'''

def terminal_colors(mode,c,program,btop_enabled=False):
    if not c or mode!='full' or (program=='btop' and not btop_enabled):
        return '#e8e8e8',[]
    # Map terminal accents and neutral shades to semantic roles.
    palette=[c['background']]+[c['accent']]*6+[c['foreground'],c['muted']]+[mix(c['accent'],c['foreground'],.25)]*6+[c['foreground']]
    return c['foreground'],palette

def btop_theme(c):
    roles={'main_bg':'background','main_fg':'foreground','title':'foreground','hi_fg':'accent',
           'selected_bg':'accent','selected_fg':'on_accent','inactive_fg':'muted',
           'graph_text':'muted','meter_bg':'border','proc_misc':'accent','div_line':'border',
           'proc_pause_bg':'accent','proc_follow_bg':'accent','proc_banner_bg':'accent',
           'proc_banner_fg':'on_accent','followed_bg':'accent','followed_fg':'on_accent'}
    values={k:c[v] for k,v in roles.items()}
    values['main_bg']=''
    for k in ('cpu_box','mem_box','net_box','proc_box'): values[k]=c['border']
    for name in ('temp','cpu','free','cached','available','used','download','upload','process'):
        for suffix,t in (('start',.35),('mid',.7),('end',1)):
            values[name+'_'+suffix]=mix(c['surface'],c['accent'],t)
    return ''.join(f'theme[{k}]="{v}"\n' for k,v in values.items())


def read_appearance(fallback='full'):
    try:
        value=json.loads((THEME_FILE.parent/'appearance.json').read_text())['style']
        return value if value in MODES else fallback
    except (OSError,ValueError,KeyError,TypeError): return fallback
