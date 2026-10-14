import unittest,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gpu
class GpuTests(unittest.TestCase):
    def test_query_cache_and_static_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'data').mkdir(); state=root/'state'
            with patch.object(gpu,'ROOT',root),patch.object(gpu,'STATE',state),patch('gpu.subprocess.run') as run:
                run.return_value=subprocess.CompletedProcess([],0,'NVIDIA GeForce RTX 4060 Laptop GPU\n','')
                self.assertEqual(gpu.gpu_name(),'NVIDIA GeForce RTX 4060 Laptop GPU')
                self.assertEqual(run.call_args.args[0],['/usr/bin/nvidia-smi','--query-gpu=name','--format=csv,noheader'])
                run.side_effect=subprocess.TimeoutExpired('nvidia-smi',3)
                self.assertEqual(gpu.gpu_name(),'NVIDIA GeForce RTX 4060 Laptop GPU')
                (root/'data/gpu.json').write_text(json.dumps({'name':'NVIDIA GeForce RTX 4070 Laptop GPU'}))
                self.assertEqual(gpu.gpu_name(),'NVIDIA GeForce RTX 4070 Laptop GPU')
    def test_invalid_names(self):
        for name in (None,'','\x1b[31mGPU','{invalid}','line\nbreak'):
            self.assertFalse(gpu.valid_name(name))
