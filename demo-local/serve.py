import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype/services/api'))
from server import Handler, Store, ThreadingHTTPServer
class DemoHandler(Handler):
    def do_GET(self):
        if self.path in ('/','/index.html'):
            body=Path(__file__).with_name('index.html').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        else:self.handle_request()
import argparse, tempfile
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8791);parser.add_argument('--db',default=str(Path(tempfile.gettempdir())/'caddie-complete-journey.sqlite3'));args=parser.parse_args()
s=ThreadingHTTPServer(('127.0.0.1',args.port),DemoHandler)
s.store=Store(args.db)
print(f'Demo http://127.0.0.1:{args.port}',flush=True)
try:s.serve_forever()
finally:s.server_close()
