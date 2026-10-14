import unittest
import tempfile
import json
import sys
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import academic,clamp_rect,default_layout,Store,ROOT,read_json,conditions,command

class AcademicTests(unittest.TestCase):
    def test_boundaries(self):
        expected={'2026-09-18':'Teaching week 6','2026-09-19':'Recess','2026-09-27':'Recess','2026-09-28':'Teaching week 7','2026-10-14':'Teaching week 9','2026-11-13':'Teaching week 13','2026-11-14':'Reading week','2026-11-21':'Examinations','2026-12-05':'Examinations','2026-12-06':'Vacation','2027-01-01':'Vacation','2027-01-11':'Teaching week 1','2027-02-20':'Recess','2027-03-01':'Teaching week 7','2027-04-16':'Teaching week 13','2027-04-17':'Reading week','2027-04-24':'Examinations','2027-05-09':'Vacation','2027-08-02':'unavailable'}
        for day,text in expected.items():
            with self.subTest(day=day): self.assertIn(text,academic(date.fromisoformat(day))[0])
    def test_coverage_has_no_gaps_or_overlap(self):
        phases=read_json(ROOT/'data/academic.json',{})['phases']
        for a,b in zip(phases,phases[1:]):
            self.assertEqual(date.fromisoformat(a['end'])+timedelta(days=1),date.fromisoformat(b['start']))
    def test_outside_coverage(self):
        self.assertIn('unavailable',academic(date(2030,1,1))[0])

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
            self.assertEqual(again.layout('laptop',1440,900)['music']['x'],50)
            self.assertFalse(again.layout('laptop',1440,900)['music']['visible'])
            self.assertNotEqual(again.layout('external',1440,900)['music']['x'],50)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
    def test_corrupt_state_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.json'; path.write_text('{broken')
            self.assertIn('btop',Store(path).layout('screen',1440,900))
            path.write_text('{"layouts": {"screen": {"music": null}}}')
            self.assertIn('music',Store(path).layout('screen',1440,900))

class IntegrationHelpersTests(unittest.TestCase):
    def test_unknown_weather_code(self): self.assertEqual(conditions(999)[1],'Weather unavailable')
    def test_subprocess_never_expands_shell(self):
        text='$(touch /tmp/glass-should-not-exist); `whoami`'
        self.assertEqual(command(['/usr/bin/printf','%s',text]),text)

if __name__=='__main__': unittest.main()
