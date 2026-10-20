from pathlib import Path
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'transaction/prepare.c'

def desc(data):return ''.join('%'+key+'%\n'+'\n'.join(value)+'\n\n' for key,value in data.items())

class PrepareOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.binary=Path(cls.tmp.name)/'prepare'
        flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer']if os.environ.get('ABI_PREPARE_SANITIZERS')=='1'else []
        subprocess.run(['cc','-std=c11','-D_GNU_SOURCE','-Wall','-Wextra','-Werror',*flags,str(SOURCE),'-lalpm','-o',str(cls.binary)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def fixture(self,folder,provide=True,architecture="aarch64"):
        root=Path(folder);(root/'root').mkdir();(root/'db/local').mkdir(parents=True);(root/'db/sync').mkdir();(root/'root/.abi-prepare-only').write_text('metadata-only\n');(root/'db/.abi-prepare-only').write_text('metadata-only\n')
        (root/'db/local/ALPM_DB_VERSION').write_text('9\n')
        for name,extra in [('old-runtime',{'PROVIDES':['runtime=1']}),('app',{'DEPENDS':['runtime']})]:
            p=root/'db/local'/(name+'-1-1');p.mkdir();(p/'desc').write_text(desc({'NAME':[name],'VERSION':['1-1'],'ARCH':['aarch64'],**extra}));(p/'files').write_text('%FILES%\n\n')
        row={'NAME':['new-runtime'],'BASE':['new-runtime'],'VERSION':['2-1'],'DESC':['fixture'],'ARCH':[architecture],'FILENAME':['new-runtime-2-1-aarch64.pkg.tar.xz'],'CSIZE':['1'],'ISIZE':['1'],'CONFLICTS':['old-runtime'],'PROVIDES':['runtime=2'] if provide else ['different-runtime=2']}
        with tarfile.open(root/'db/sync/fixture.db','w:gz')as archive:
            data=desc(row).encode();member=tarfile.TarInfo('new-runtime-2-1/desc');member.size=len(data);archive.addfile(member,io.BytesIO(data))
        (root/'targets').write_text('fixture\tnew-runtime\t2-1\n');(root/'protected').write_text('');(root/'scenario').write_text('new-runtime\told-runtime\n');(root/'repositories').write_text('fixture\n')
        return root
    def run_engine(self,root):
        run=subprocess.run([str(self.binary),str(root/'root'),str(root/'db'),str(root/'targets'),str(root/'protected'),str(root/'scenario'),str(root/'repositories')],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr);return json.loads(run.stdout)
    def test_actual_libalpm_scenario_removes_only_exact_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.fixture(folder);result=self.run_engine(root)
            self.assertTrue(result['prepared'],result)
            self.assertEqual([p['name']for p in result['remove']],['old-runtime'])
            self.assertEqual([p['name']for p in result['add']],['new-runtime'])
            self.assertFalse(result['committed'])
            self.assertTrue((root/'db/local/old-runtime-1-1/desc').exists())

    def test_actual_libalpm_declines_unlisted_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.fixture(folder);(root/'scenario').write_text('');result=self.run_engine(root)
            self.assertFalse(result['prepared']);self.assertEqual(result['prepare_exit'],-1)
            self.assertTrue(result['conflict_checks']);self.assertEqual(result['questions'][0]['answer'],0)
    def test_actual_libalpm_protects_held_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.fixture(folder);(root/'protected').write_text('old-runtime\n');result=self.run_engine(root)
            self.assertFalse(result['prepared']);self.assertEqual(result['questions'][0]['answer'],0)
            self.assertFalse(result['protected_changed'])
    def test_actual_libalpm_rejects_broken_reverse_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.fixture(folder,provide=False);result=self.run_engine(root)
            self.assertFalse(result['prepared']);self.assertEqual(result['prepare_exit'],-1)
            self.assertTrue(result['dependency_checks'])
            self.assertTrue(any(d.get('target')=='app' and d.get('dependency')=='runtime' for d in result['details']))
    def test_helper_has_no_commit_or_sysupgrade_import(self):
        run=subprocess.run(['nm','-u',str(self.binary)],check=True,capture_output=True,text=True)
        self.assertIn('alpm_trans_prepare',run.stdout)
        self.assertNotIn('alpm_trans_commit',run.stdout)
        self.assertNotIn('alpm_sync_sysupgrade',run.stdout)
        self.assertNotIn('alpm_pkg_load',run.stdout)

    def test_actual_libalpm_rejects_wrong_architecture(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.fixture(folder,architecture='x86_64');result=self.run_engine(root)
            self.assertFalse(result['prepared']);self.assertEqual(result['prepare_exit'],-1)
            self.assertIn('architecture',result['error'])
