import copy
import importlib.util
import io
import pathlib
import tarfile
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('audit', pathlib.Path(__file__).parents[1]/'audit_transaction.py')
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
F='A'*40; G='B'*40

class AuditTests(unittest.TestCase):
    def test_each_signer_uses_own_anchor(self):
        keys={'anchors':{F:['one'],G:['two']},'revoked':set()}
        for fpr,ring in ((F,'one'),(G,'two')):
            result=a.signature_result(0,f'[GNUPG:] VALIDSIG {fpr} 2026-01-01 1 0 4 0 22 8 00 {fpr}',keys)
            self.assertEqual(result['retained_explicit_anchor_keyrings'],[ring])
    def test_missing_trust_not_invented(self):
        result=a.signature_result(0,f'[GNUPG:] VALIDSIG {F} date 1 0 4 0 22 8 00 {F}',{'anchors':{},'revoked':set()})
        self.assertTrue(result['trust'].startswith('BLOCKED'))
    def test_bad_expired_missing_revoked_rejected(self):
        for tag in a.BAD_SIG:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                a.signature_result(0,f'[GNUPG:] VALIDSIG {F} date 1 0 4 0 22 8 00 {F}\n[GNUPG:] {tag} {F}',{'anchors':{F:['one']},'revoked':set()})
        with self.assertRaises(ValueError):
            a.signature_result(0,f'[GNUPG:] VALIDSIG {F} date 1 0 4 0 22 8 00 {F}',{'anchors':{F:['one']},'revoked':{F}})
    def test_nonzero_with_validsig_rejected(self):
        with self.assertRaises(ValueError): a.signature_result(1,f'[GNUPG:] VALIDSIG {F} date 1 0 4 0 22 8 00 {F}',{})
    def test_hook_is_data_and_boot_sensitive(self):
        row=a.hook_data('test.hook',b'[Trigger]\nType = Path\nTarget = boot/*\n[Action]\nExec = /usr/bin/mkinitcpio -P\nNeedsTargets\n')
        self.assertTrue(row['boot_sensitive_text']); self.assertEqual(row['sections'][1]['fields']['NeedsTargets'],[True])
    def archive(self, entries):
        folder=tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup); path=pathlib.Path(folder.name)/'test.tar'
        with tarfile.open(path,'w') as t:
            for name,data,kind in entries:
                m=tarfile.TarInfo(name);m.type=kind;m.size=len(data);t.addfile(m,io.BytesIO(data))
        return path
    def test_signed_identity_and_install_data(self):
        path=self.archive([('.PKGINFO',b'pkgname = test\npkgver = 1-1\narch = aarch64\n',tarfile.REGTYPE),('.INSTALL',b'echo never-run\n',tarfile.REGTYPE)])
        row={'name':'test','version':'1-1','architecture':'aarch64'}
        self.assertEqual(a.archive_data(path,row)['install_scripts'][0]['text'],'echo never-run\n')
        row['architecture']='x86_64'
        with self.assertRaises(ValueError):a.archive_data(path,row)
    def test_symlink_metadata_and_traversal_rejected(self):
        for name,kind in [('.PKGINFO',tarfile.SYMTYPE),('../bad',tarfile.REGTYPE)]:
            with self.assertRaises(ValueError): a.archive_data(self.archive([(name,b'',kind)]),{})
    def test_protected_plan_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);(root/'evidence/repositories').mkdir(parents=True)
            db=root/'evidence/repositories/test.db';db.write_bytes(b'fixture')
            plan={'schema':1,'deployable':False,'actions':[],'resolved_transaction':[{'name':'linux-aurora'}],'transaction_package_count':1,'repositories':[{'name':'test','sha256':a.sha(db)}]}
            with self.assertRaisesRegex(ValueError,'protected'):
                a.pin_rows(plan,{'test':{'sha256':a.sha(db)}},root,lambda p,d:[],lambda n:n=='linux-aurora')
    def test_size_or_digest_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source=pathlib.Path(folder)/'source'; source.write_bytes(b'wrong')
            with self.assertRaises(ValueError):a.download(source.as_uri(),pathlib.Path(folder)/'out',5,'0'*64)
    def test_hook_package_path_and_negation(self):
        h=a.hook_data('a.hook',b'[Trigger]\nOperation = Upgrade\nType = Package\nTarget = *\nTarget = !safe\n[Action]\nExec = /usr/bin/guard\n')
        packages=[{'name':'safe','payload_paths':['boot/a']},{'name':'other','payload_paths':['usr/bin/abc']}]
        out=a.hook_matches(h,packages,{'safe','other'})
        self.assertEqual([x['package'] for x in out['matches']],['other'])
        h=a.hook_data('b.hook',b'[Trigger]\nOperation = Install\nType = Path\nTarget = boot/*\n[Action]\nExec = /usr/bin/guard\n')
        self.assertTrue(a.hook_matches(h,packages,set())['would_match_incoming_paths'])
        self.assertFalse(a.hook_matches(h,packages,{'safe','other'})['would_match_incoming_paths'])
    def test_baseline_override_and_null_mask(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            for p in a.HOOK_ROOTS:(root/p).mkdir(parents=True)
            (root/a.HOOK_ROOTS[0]/'a.hook').write_text('[Action]\nExec = /usr/bin/bad\n')
            (root/a.HOOK_ROOTS[1]/'a.hook').symlink_to('/dev/null')
            out=a.baseline_hooks(root)
            self.assertEqual(len(out['inventory']),2);self.assertEqual(len(out['effective']),1)
            self.assertTrue(out['effective'][0]['disabled'])
    def test_image_manifest_rejects_wrong_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);(root/'manifest.json').write_text('{"image_sha256":"wrong","root":256}')
            with self.assertRaises(ValueError):a.image_snapshot(root,root)
    def test_exact_db_payload_architecture_and_repository_pins(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);(root/'evidence/repositories').mkdir(parents=True)
            db=root/'evidence/repositories/test.db';db.write_bytes(b'fixture')
            row={'name':'safe','version':'1-1','architecture':'aarch64','filename':'safe.pkg.tar.zst','sha256':'a'*64,'repository':'test'}
            fields={'NAME':['safe'],'VERSION':['1-1'],'ARCH':['aarch64'],'FILENAME':['safe.pkg.tar.zst'],'SHA256SUM':['a'*64],'CSIZE':['12'],'PGPSIG':['AA==']}
            plan={'schema':1,'deployable':False,'actions':[],'resolved_transaction':[row],'transaction_package_count':1,'repositories':[{'name':'test','sha256':a.sha(db)}]}
            prov={'test':{'sha256':a.sha(db),'url':'https://example.invalid/test.db'}}
            self.assertEqual(len(a.pin_rows(plan,prov,root,lambda p,d:[fields],lambda n:False)),1)
            for key,value in [('architecture','x86_64'),('version','2-1'),('filename','../escape'),('sha256','b'*64)]:
                modified=copy.deepcopy(plan);modified['resolved_transaction'][0][key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):a.pin_rows(modified,prov,root,lambda p,d:[fields],lambda n:False)
            db.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'digest'):a.pin_rows(plan,prov,root,lambda p,d:[fields],lambda n:False)
    def test_name_safe_package_still_triggers_boot_effect_guard(self):
        h=a.hook_data('etc/pacman.d/hooks/90-mkinitcpio-install.hook',b'[Trigger]\nOperation = Upgrade\nType = Path\nTarget = usr/lib/initcpio/*\n[Action]\nExec = /usr/share/libalpm/scripts/limine-mkinitcpio-install\n')
        rows=[{'name':'plymouth','status':'WORKS','payload_paths':['usr/lib/initcpio/install/plymouth']}]
        matches=[a.hook_matches(h,rows,{'plymouth'})]
        gate=a.execution_gate(rows,{'effective':[h]},matches)
        self.assertFalse(gate['execution_ready'])
        self.assertEqual(gate['boot_effects'][0]['effect'],'boot_artifact_generation')
        self.assertEqual(gate['boot_effects'][0]['incoming_matches'][0]['matching_values'],['usr/lib/initcpio/install/plymouth'])
        self.assertIn('incoming_payload_triggers_boot_related_hooks',[b['reason'] for b in gate['execution_blockers']])
        clean=[{'name':'plymouth','status':'WORKS','payload_paths':['usr/bin/plymouth']}]
        self.assertEqual(a.execution_gate(clean,{'effective':[h]},[a.hook_matches(h,clean,{'plymouth'})])['boot_effects'],[])
    def test_snapshot_manifest_does_not_hash_itself_or_follow_links(self):
        import sys
        sys.path.insert(0,str(pathlib.Path(__file__).parents[1]))
        import prepare_image
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);(root/'data').write_bytes(b'owned')
            (root/'manifest.json').write_text('old manifest')
            (root/'link').symlink_to('/dev/null')
            first=prepare_image.inventory(root)
            (root/'manifest.json').write_text('new manifest')
            self.assertEqual(first,prepare_image.inventory(root))
            self.assertNotIn('manifest.json',first)
            self.assertEqual(first['link'],{'symlink':'/dev/null'})
    def test_snapshot_unmanifested_hook_rejected(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            (root/'manifest.json').write_text(json.dumps({'image_sha256':'f6ceb11ef79914eaa10cc07637c929a99afe5982d216d8b89905c86e863b2491','root':256,'image_bytes':14344519680,'entries':{}}))
            (root/'rogue.hook').write_text('[Action]\nExec = /usr/bin/false\n')
            with self.assertRaisesRegex(ValueError,'unmanifested'):a.image_snapshot(root,root)
    def test_non_deployable_guard(self):
        with self.assertRaises(ValueError):a.pin_rows({'schema':1,'deployable':True,'actions':[]},{},None,None,None)

if __name__=='__main__': unittest.main()
