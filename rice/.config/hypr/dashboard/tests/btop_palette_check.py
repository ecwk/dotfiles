"""Opt-in actual btop terminal color regression check; uses temporary configuration."""
import os,pty,subprocess,termios,fcntl,struct,select,time,json,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from theme import btop_theme
from core import ROOT
sandbox=tempfile.TemporaryDirectory(prefix='btop-colors-')
state=Path(sandbox.name)
colors=dict(background='#101012',surface='#202026',foreground='#e1d2c3',muted='#a1a2a3',border='#414243',accent='#ab8cde',on_accent='#121314')
(state/'walltheme.theme').write_text(btop_theme(colors))
(state/'btop.conf').write_text((ROOT/'data/btop.conf').read_text().replace('color_theme = "Default"',f'color_theme = "{state}/walltheme.theme"'))
def capture(extra):
    master,slave=pty.openpty()
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',32,110,0,0))
    p=subprocess.Popen(['/usr/bin/btop','--config',str(state/'btop.conf'),*extra],stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='xterm-256color'),start_new_session=True)
    os.close(slave); data=b''; end=time.monotonic()+3
    try:
        while time.monotonic()<end:
            if select.select([master],[],[],.1)[0]:
                try: chunk=os.read(master,65536)
                except OSError: break
                data+=chunk
                if b'\x1b[6n' in chunk: os.write(master,b'\x1b[1;1R')
        return data
    finally:
        p.terminate()
        try: p.wait(timeout=2)
        except subprocess.TimeoutExpired: p.kill(); p.wait()
        os.close(master)
def sequence(color):
    return ('\x1b[38;2;'+';'.join(str(int(color[i:i+2],16)) for i in (1,3,5))+'m').encode()
before=capture([])
after=capture(['--themes-dir',str(state)])
for role in ('foreground','accent'):
    code=sequence(colors[role]); print(role,'before:',code in before,'after:',code in after)
    assert code in after,'Btop did not emit themed '+role
assert sequence(colors['foreground']) not in before,'Baseline did not reproduce the bug'
print('PASS: actual btop ANSI output uses walltheme text and accent colors')

sandbox.cleanup()
