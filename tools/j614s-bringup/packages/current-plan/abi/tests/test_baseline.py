from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from baseline import description_identity,assert_identity

class CompleteBaseline(unittest.TestCase):
    def test_actual_nonheld_description_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('held-1-1','nonheld-2-1'):
                (root/name).mkdir();(root/name/'desc').write_bytes(b'%NAME%\n'+name.encode()+b'\n')
            expected=description_identity(root);assert_identity(root,expected)
            (root/'nonheld-2-1/desc').write_bytes(b'%NAME%\nchanged-nonheld\n')
            with self.assertRaisesRegex(ValueError,'complete baseline description identity differs'):assert_identity(root,expected)
    def test_added_and_removed_description_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a-1').mkdir();(root/'a-1/desc').write_bytes(b'original')
            expected=description_identity(root);(root/'a-1/desc').unlink()
            with self.assertRaises(ValueError):assert_identity(root,expected)
    def test_symlink_description_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a-1').mkdir();(root/'value').write_bytes(b'original');(root/'a-1/desc').symlink_to('../value')
            with self.assertRaisesRegex(ValueError,'regular description'):description_identity(root)
if __name__=='__main__':unittest.main()
