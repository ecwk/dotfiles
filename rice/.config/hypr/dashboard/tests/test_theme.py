import unittest,json,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from theme import read_palette,css,terminal_colors,btop_theme,ROLES

class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.c=dict(zip(ROLES,['#101010','#202020','#eeeeee','#aaaaaa','#333333','#cc88aa','#220011']))
    def test_validates_public_roles_and_ignores_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'current.json'
            p.write_text(json.dumps({'colors':dict(self.c,extra='ignored'),'future':True}))
            self.assertEqual(read_palette(p),self.c)
            for value in [None,[],{}, {'colors':dict(self.c,accent='red; }')}, {'colors':dict(self.c,accent=2)}]:
                p.write_text(json.dumps(value)); self.assertIsNone(read_palette(p))
            p.write_text('{broken'); self.assertIsNone(read_palette(p))
    def test_modes_and_btop_exception(self):
        self.assertEqual(css('original',self.c),'')
        self.assertNotIn('.glass',css('accents',self.c))
        self.assertIn('.glass',css('full',self.c))
        for mode in ('original','accents'):
            self.assertEqual(terminal_colors(mode,self.c,'btop',True),('#e8e8e8',[]))
        self.assertEqual(terminal_colors('full',self.c,'btop',False),('#e8e8e8',[]))
        self.assertEqual(len(terminal_colors('full',self.c,'btop',True)[1]),16)
        self.assertIn('theme[selected_fg]="'+self.c['on_accent']+'"',btop_theme(self.c))
        self.assertIn('theme[main_bg]=""',btop_theme(self.c))
    def test_absent_palette_falls_back(self):
        self.assertEqual(css('full',None),'')
        self.assertEqual(terminal_colors('full',None,'fastfetch'),('#e8e8e8',[]))

if __name__=='__main__': unittest.main()
