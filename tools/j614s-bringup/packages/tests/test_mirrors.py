import http.server
import json
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]))
import exhaust_official_mirrors as m

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if 'missing' in self.path:
            self.send_response(404);self.end_headers();self.wfile.write(b'missing')
        else:
            self.send_response(200);self.end_headers();self.wfile.write(b'wrong')
    def log_message(self,*args):pass

class MirrorTests(unittest.TestCase):
    def test_official_domain_list_rejects_unreviewed_or_duplicate(self):
        for data in ({'data':[]},{'data':[['X','X','attacker.invalid','']]},{'data':[['X','X','de.mirror.archlinuxarm.org','']]*2}):
            with self.assertRaises(ValueError):m.published_domains(json.dumps(data))
        self.assertEqual(m.published_domains(json.dumps({'data':[['X','X','de.mirror.archlinuxarm.org','']]})),['de.mirror.archlinuxarm.org'])
    def test_page_parser_records_version_without_substitution(self):
        result=m.package_page(b'<h1>marisa 0.3.1-2</h1><a href="http://mirror.archlinuxarm.org/aarch64/extra/marisa-0.3.1-2-aarch64.pkg.tar.xz">Download</a>')
        self.assertEqual(result['repository'],'extra');self.assertFalse(result['new_version_payload_requested'])
        with self.assertRaises(ValueError):m.package_page(b'<h1>missing download</h1>')
    def test_real_http_404_and_wrong_bytes_never_reach_signature_qualification(self):
        with socketserver.TCPServer(('127.0.0.1',0),Handler) as server,tempfile.TemporaryDirectory() as folder:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                domain='127.0.0.1:'+str(server.server_address[1])
                for filename,size,expected in [('missing',5,'HTTPError'),('oversize',1,'CSIZE'),('digest',5,'SHA mismatch')]:
                    row={'name':'fixture','version':'1-1','filename':filename,'sha256':'0'*64,'architecture':'aarch64','repository':'extra'}
                    out=m.probe((row,{'CSIZE':[str(size)]},''),domain,Path(folder),{})
                    self.assertEqual(out['status'],'BLOCKED');self.assertIn(expected,out['failure'])
                    self.assertNotIn('pinned_signature_qualification',out)
            finally:server.shutdown();thread.join()

if __name__=='__main__':unittest.main()
