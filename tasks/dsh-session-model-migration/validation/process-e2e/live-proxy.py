#!/usr/bin/env python3
"""Private forwarding fixture for live acceptance. It never scripts model output.
Run on the credential-owning machine; point the DSH test at its IPv6 address.
Credentials are read from a file and appear only in the upstream request URL.
"""
import argparse, ast, http.server, json, socket, threading, time
import urllib.request, urllib.error, urllib.parse, uuid
from pathlib import Path
from dotenv import dotenv_values

p=argparse.ArgumentParser();p.add_argument('--env-file',type=Path,required=True);p.add_argument('--key-index',type=int,default=1);p.add_argument('--port',type=int,default=20231);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
keys=ast.literal_eval(dotenv_values(args.env_file)['GPT56_EXPERIMENT_API_KEYS']);secret=keys[args.key_index]
args.out.mkdir(parents=True,exist_ok=True)
records=[];lock=threading.Lock();affinity=uuid.uuid4().hex
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path!='/evidence':self.send_error(404);return
        data=json.dumps(records).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        routes={'/source/chat/completions':'https://aidp.bytedance.net/api/modelhub/online/v2/crawl','/destination/chat/completions':'https://aidp.bytedance.net/api/modelhub/online/v2/crawl','/source/responses':'https://aidp.bytedance.net/api/modelhub/online/responses','/destination/responses':'https://aidp.bytedance.net/api/modelhub/online/responses'}
        if self.path not in routes:self.send_error(404);return
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        # Fixed model scope; an accidental ancillary request cannot spend on other routes.
        if body.get('model') not in ('gpt-6-astra','gpt-5.6-sol','ali-deepseek-v4-pro','Minimax-M3'):self.send_error(400);return
        route_secret=keys[0] if body['model']=='gpt-5.6-sol' else secret
        start=time.time();record={'path':self.path,'body':body,'started_at':start,'affinity':affinity+'-'+body['model']}
        raw=b''
        try:
            req=urllib.request.Request(routes[self.path]+'?ak='+urllib.parse.quote(route_secret,safe=''),data=json.dumps(body).encode(),headers={'Content-Type':'application/json','extra':json.dumps({'session_id':record['affinity']})})
            with urllib.request.urlopen(req,timeout=180) as upstream:
                record['status']=upstream.status
                # Collect complete upstream SSE before delivering, preserving all events.
                # This is acceptance, not a latency benchmark.
                raw=upstream.read()
                kind=upstream.headers.get('Content-Type','application/json')
        except urllib.error.HTTPError as error:
            record['status']=error.code;raw=error.read();kind='application/json'
        except Exception as error:
            record['status']=502;raw=json.dumps({'error':type(error).__name__}).encode();kind='application/json'
        record.update(elapsed=time.time()-start,response=raw.decode(errors='replace').replace(secret,'<redacted>').replace(keys[0],'<redacted>'))
        with lock:
            records.append(record)
            (args.out/'live-wire.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
        self.send_response(record['status']);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.end_headers()
        try:self.wfile.write(raw)
        except BrokenPipeError:pass
class Server(http.server.ThreadingHTTPServer):address_family=socket.AF_INET6
server=Server(('::',args.port),Handler)
print(json.dumps({'listening':args.port,'models':['gpt-6-astra','gpt-5.6-sol','ali-deepseek-v4-pro','Minimax-M3'],'apis':['v2/crawl','responses']}),flush=True)
try:server.serve_forever()
finally:server.server_close()
