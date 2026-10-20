from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from filesystem import seal_tree,validate_tree,write_cache,read_cache,verify_or_write

class Provenance(unittest.TestCase):
    def test_actual_file_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'file').write_bytes(b'original')
            seal_tree(root,{'source':'fixture'})
            validate_tree(root,{'source':'fixture'})
            (root/'file').write_bytes(b'changed!')
            with self.assertRaisesRegex(ValueError,'identities changed'):validate_tree(root,{'source':'fixture'})
    def test_actual_link_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a').symlink_to('original');seal_tree(root,{'source':'fixture'})
            (root/'a').unlink();(root/'a').symlink_to('changed')
            with self.assertRaisesRegex(ValueError,'identities changed'):validate_tree(root,{'source':'fixture'})
    def test_new_file_and_provenance_change_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);seal_tree(root,{'source':'fixture'})
            with self.assertRaisesRegex(ValueError,'provenance differs'):validate_tree(root,{'source':'another'})
            (root/'new').write_bytes(b'new ELF-like data')
            with self.assertRaisesRegex(ValueError,'identities changed'):validate_tree(root,{'source':'fixture'})
    def test_actual_cache_mutation_rejected_before_decode(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.json.gz';write_cache(path,{'value':'original'})
            self.assertEqual(read_cache(path),{'value':'original'})
            data=bytearray(path.read_bytes());data[len(data)//2]^=1;path.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'cache integrity changed'):read_cache(path)
    def test_provider_reuse_checks_exact_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'provider.elf';verify_or_write(path,b'original ELF data')
            verify_or_write(path,b'original ELF data')
            path.write_bytes(b'changed! ELF data')
            with self.assertRaisesRegex(ValueError,'provider bytes differ'):verify_or_write(path,b'original ELF data')

    def test_immutable_cache_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.json.gz';write_cache(path,{'value':'original'})
            with self.assertRaisesRegex(ValueError,'destination exists'):write_cache(path,{'value':'changed'})
if __name__=='__main__':unittest.main()
