import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_plan import safe_member,resolve,dependency

class VirtualFilesystem(unittest.TestCase):
    def test_no_archive_traversal(self):
        for name in ('../escape','usr/../../escape','/absolute'):
            with self.subTest(name=name),self.assertRaises(ValueError):safe_member(name)
        self.assertEqual(safe_member('./usr/lib/a.so'),'usr/lib/a.so')
    def test_image_absolute_and_relative_links_stay_virtual(self):
        entries={'usr/lib/a.so':{'link':'a.so.1'},'usr/lib/a.so.1':{'link':'/usr/lib/a.so.1.2'},'usr/lib/a.so.1.2':{'owner':'fixture'}}
        self.assertEqual(resolve(entries,'/usr/lib/a.so'),('usr/lib/a.so.1.2',{'owner':'fixture'}))
    def test_symlink_loop_rejected(self):
        with self.assertRaises(ValueError):resolve({'usr/lib/a':{'link':'a'}},'/usr/lib/a')
    def test_symlink_escape_rejected(self):
        with self.assertRaises(ValueError):resolve({'a':{'link':'../../etc/passwd'}},'/a')
    def test_origin_runpath_precedes_default(self):
        elf={'runpath':['$ORIGIN/../lib'],'rpath':[]}
        entries={'opt/app/lib/a.so':{'owner':'private'},'usr/lib/a.so':{'owner':'global'}}
        self.assertEqual(dependency(entries,'opt/app/bin/main',elf,'a.so'),('opt/app/lib/a.so',{'owner':'private'},None))
    def test_unsupported_token_does_not_fall_through(self):
        elf={'runpath':['$LIB'],'rpath':[]}
        self.assertEqual(dependency({'usr/lib/a.so':{}},'usr/bin/main',elf,'a.so'),(None,None,'unsupported dynamic loader token'))
