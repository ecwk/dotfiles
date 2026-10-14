import unittest
import tempfile
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import clamp_rect,default_layout,Store,ROOT,read_json,command,PRESETS,preset_layout

class LayoutTests(unittest.TestCase):
    def test_offscreen_and_bad_dimensions(self):
        self.assertEqual(clamp_rect({'x':3000,'y':-100,'w':9999,'h':float('nan')},800,600),{'x':0,'y':0,'w':800,'h':120,'visible':True})
    def test_small_display_bounds(self):
        for dims in [(1440,900),(1920,1080),(800,600),(360,240)]:
            for r in default_layout(*dims).values():
                self.assertLessEqual(r['x']+r['w'],dims[0]); self.assertLessEqual(r['y']+r['h'],dims[1])
    def test_default_panels_do_not_overlap(self):
        values=list(default_layout(1440,900).values())
        for i,a in enumerate(values):
            for b in values[i+1:]:
                self.assertTrue(a['x']+a['w']<=b['x'] or b['x']+b['w']<=a['x'] or a['y']+a['h']<=b['y'] or b['y']+b['h']<=a['y'])
    def test_persistence_and_monitor_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.json'; store=Store(path)
            saved=store.layout('laptop',1440,900); saved['music']['x']=50; saved['music']['visible']=False
            store.data['layouts']['laptop']=saved; store.save(); again=Store(path)
            self.assertNotEqual(again.layout('laptop',1440,900)['music']['x'],50)
            self.assertFalse(again.layout('laptop',1440,900)['music']['visible'])
            self.assertNotEqual(again.layout('external',1440,900)['music']['x'],50)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
    def test_all_presets_and_centering(self):
        for name in PRESETS:
            rects=list(preset_layout(name,1440,900).values())
            for i,a in enumerate(rects):
                self.assertGreaterEqual(a['x'],0); self.assertGreaterEqual(a['y'],0)
                self.assertLessEqual(a['x']+a['w'],1440); self.assertLessEqual(a['y']+a['h'],900)
                for b in rects[i+1:]:
                    self.assertTrue(a['x']+a['w']<=b['x'] or b['x']+b['w']<=a['x'] or a['y']+a['h']<=b['y'] or b['y']+b['h']<=a['y'],name)
        r=default_layout(1440,900)
        self.assertLessEqual(abs(r['music']['y']-(900-r['btop']['y']-r['btop']['h'])),1)
    def test_preset_selection_per_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'settings.json')
            store.data['layout_presets']={'laptop':'compact-bento','external':'floating-corners'}
            store.save(); loaded=Store(store.path)
            self.assertEqual(loaded.layout('laptop',1440,900),preset_layout('compact-bento',1440,900))
            self.assertEqual(loaded.layout('external',1440,900),preset_layout('floating-corners',1440,900))
    def test_corrupt_state_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.json'; path.write_text('{broken')
            self.assertIn('btop',Store(path).layout('screen',1440,900))
            path.write_text('{"layouts": {"screen": {"music": null}}}')
            self.assertIn('music',Store(path).layout('screen',1440,900))

class IntegrationHelpersTests(unittest.TestCase):
    def test_subprocess_never_expands_shell(self):
        text='$(touch /tmp/glass-should-not-exist); `whoami`'
        self.assertEqual(command(['/usr/bin/printf','%s',text]),text)

if __name__=='__main__': unittest.main()
