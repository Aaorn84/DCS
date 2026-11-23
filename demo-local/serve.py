import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype/services/api'))
from server import Handler, Store, ThreadingHTTPServer
from shared_core import call
call('capabilities')
class DemoHandler(Handler):
    def do_GET(self):
        if self.path in ('/','/index.html','/international.html'):
            body=Path(__file__).with_name('international.html' if self.path=='/international.html' else 'index.html').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
        else:self.handle_request()
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8791);parser.add_argument('--database-url',default=None);args=parser.parse_args()
s=ThreadingHTTPServer(('127.0.0.1',args.port),DemoHandler)
s.store=Store(args.database_url)
print(f'Demo http://127.0.0.1:{args.port}',flush=True)
try:s.serve_forever()
finally:s.server_close()
