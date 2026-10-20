import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import propose as p
import qualify_payloads as q
SOURCE=Path(os.environ.get('J614S_OMARCHY_SOURCE',
    str(Path(__file__).resolve().parents[3]/'omarchy')))


def fixture_db(path, rows):
    with tarfile.open(path,'w') as archive:
        for row in rows:
            text=''.join('%'+key+'%\n'+'\n'.join(value)+'\n\n' for key,value in row.items())
            data=text.encode();info=tarfile.TarInfo(row['NAME'][0]+'-'+row['VERSION'][0]+'/desc');info.size=len(data)
            archive.addfile(info,io.BytesIO(data))


def fields(name,*,arch='aarch64',depends=(),provides=()):
    return {'NAME':[name],'VERSION':['1-1'],'ARCH':[arch],'FILENAME':[name+'-1-1-'+arch+'.pkg.tar.zst'],
            'SHA256SUM':['a'*64],'CSIZE':['12'],'ISIZE':['24'],'DEPENDS':list(depends),'PROVIDES':list(provides)}

class CurrentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records,cls.protected,cls.resolver,cls.planner,cls.old=p.original_inputs(SOURCE)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def review(self,rows,direct='safe'):
        path=self.root/'extra.db';fixture_db(path,rows)
        index,provenance=self.planner.index_repositories([('extra',path)])
        return path,{'schema':1,'architecture':'aarch64','deployable':False,'actions':[],
                     'repositories':provenance,'protected_installed_pins':{},'held_requests':[],
                     'unresolved_requests':[],'resolved_requests':[{'requested':direct,'resolved':direct,'candidate':index[direct]}]}
    def baseline(self):
        root=self.root/'baseline';(root/'old-1-1').mkdir(parents=True)
        (root/'ALPM_DB_VERSION').write_text('9\n')
        (root/'old-1-1/desc').write_text('%NAME%\nold\n\n%VERSION%\n1-1\n\n%ARCH%\naarch64\n\n')
        return root
    def test_actual_c_pacman_print_resolves_dependency_in_disposable_state(self):
        db,review=self.review([fields('safe',depends=['dep>=1']),fields('dep')])
        result=self.resolver.resolve(review,[('extra',db)],self.baseline(),self.root/'solver')
        self.assertEqual(result['print_exit'],0)
        self.assertEqual({r['name'] for r in result['resolved_transaction']},{'safe','dep'})
        self.assertFalse(result['deployable']);self.assertEqual(result['actions'],[])
    def test_actual_c_resolver_refuses_protected_dependency(self):
        db,review=self.review([fields('safe',depends=['linux-aurora>=1']),fields('linux-aurora')])
        try:result=self.resolver.resolve(review,[('extra',db)],self.baseline(),self.root/'solver')
        except ValueError as error:
            self.assertIn('protected',str(error));return
        self.assertNotEqual(result['print_exit'],0)
        self.assertEqual(result['metadata_resolution'],'BLOCKED')
        self.assertIn('could not satisfy dependencies',result['resolver_error'])
        self.assertIn("linux-aurora>=1",(self.root/'solver/stdout.txt').read_text())
    def test_actual_c_resolver_rejects_changed_db_before_print(self):
        db,review=self.review([fields('safe')]);db.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'identity changed'):
            self.resolver.resolve(review,[('extra',db)],self.baseline(),self.root/'solver')
        self.assertFalse((self.root/'solver').exists())
    def test_actual_c_parser_rejects_unknown_and_protected_print_rows(self):
        row={'repository':'extra','name':'safe','version':'1-1','filename':'safe.pkg','sha256':'a'*64,'architecture':'aarch64'}
        packages={('extra','safe','1-1','safe.pkg'):row}
        self.assertEqual(self.resolver.parse_transaction('safe\t1-1\textra\tsafe.pkg\n',packages),[row])
        for output in ('safe\t2-1\textra\tsafe.pkg\n','linux-aurora\t1-1\textra\tlinux.pkg\n','safe\t1-1\textra\tsafe.pkg\textra\n'):
            with self.subTest(output=output),self.assertRaises(ValueError):self.resolver.parse_transaction(output,packages)
    def test_recorded_mapping_never_silently_replaced_by_current_provider(self):
        path=self.root/'extra.db';fixture_db(path,[fields('different',provides=['safe'])])
        old={'resolved_requests':[{'requested':'safe','candidate':{'name':'safe'},'resolved':'safe'}]}
        review,diffs=p.review_for_metadata(old,[('extra',path)],self.planner)
        self.assertEqual(review['resolved_requests'],[])
        self.assertEqual(review['unresolved_requests'][0]['canonical'],'safe')
        self.assertEqual(diffs,[])
    def test_signed_dependency_and_metadata_mismatch_rejected(self):
        db=fields('safe',depends=['actual>=1']);info={'depend':['actual>=1'],'size':['24']}
        # Only signed metadata fields are compared here; signed identity is checked separately by the shared archive verifier.
        self.assertEqual(q.signed_metadata(db,info)['status'],'WORKS')
        for name,value in [('depend',['other']),('size',['25']),('provides',['unexpected'])]:
            wrong=copy.deepcopy(info);wrong[name]=value
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'disagrees'):q.signed_metadata(db,wrong)
    def test_diff_never_silently_replaces_historical_rows(self):
        old=[{'name':'same','version':'1'},{'name':'gone','version':'1'}]
        new=[{'name':'same','version':'2'},{'name':'added','version':'1'}]
        result=p.transaction_diff(old,new)
        self.assertEqual(result['changed'][0]['old']['version'],'1');self.assertEqual(old[0]['version'],'1')
        self.assertEqual(result['added'][0]['name'],'added');self.assertEqual(result['removed'][0]['name'],'gone')
    def test_recorded_alias_requires_signed_provider_claim(self):
        review={'resolved_requests':[{'requested':'dotnet-runtime','candidate':{'name':'dotnet-runtime-bin'}}]}
        package={'name':'dotnet-runtime-bin','status':'WORKS','sha256':'a'*64,'signed_pkginfo':{'provides':['dotnet-runtime=10.0.13']}}
        self.assertTrue(q.alias_evidence(review,[package],self.root)[0]['status'].startswith('WORKS'))
        package['signed_pkginfo']['provides']=[]
        result=q.alias_evidence(review,[package],self.root)[0]
        self.assertEqual(result['status'],'BLOCKED');self.assertIn('provider claim missing',result['failure'])
    def test_current_metadata_unresolved_authentication_cannot_qualify_payloads(self):
        from propose import ORDER
        provenance={};repositories=[]
        for name in ORDER:
            db=self.root/(name+'.db');fixture_db(db,[])
            digest=hashlib.sha256(db.read_bytes()).hexdigest()
            repositories.append({'name':name,'sha256':digest})
            provenance[name]={'sha256':digest,'metadata_authentication':'UNRESOLVED signer trust'}
        proposal={'deployable':False,'execution_ready':False,'print_exit':0,'repositories':repositories,'resolved_transaction':[]}
        with self.assertRaisesRegex(ValueError,'unresolved metadata trust'):
            q.exact_items(proposal,provenance,self.root,self.records,self.protected)
    def test_signed_redirect_query_not_persisted_and_credentials_rejected(self):
        self.assertEqual(p.safe_url('https://example.org/payload?sig=temporary#fragment'),'https://example.org/payload')
        with self.assertRaises(ValueError):p.safe_url('https://user:password@example.org/payload')

if __name__=='__main__':unittest.main()
