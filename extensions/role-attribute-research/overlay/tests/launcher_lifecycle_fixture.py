"""Synthetic service for testing launcher-owned Windows process trees, no game."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

folder = Path(os.environ['FM27_DESKTOP_DATA'])

if '--leaf' in sys.argv:
    (folder / 'leaf.pid').write_text(str(os.getpid()))
    time.sleep(120)
elif '--child' in sys.argv:
    subprocess.Popen([sys.executable, __file__, '--leaf'], creationflags=subprocess.CREATE_NO_WINDOW)
    (folder / 'child.pid').write_text(str(os.getpid()))
    time.sleep(120)
else:
    subprocess.Popen([sys.executable, __file__, '--child'], creationflags=subprocess.CREATE_NO_WINDOW)
    (folder / 'server.pid').write_text(str(os.getpid()))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            data = {'engine': 'original_native', 'synthetic_lifecycle_test': True,
                    'seen': True, 'busy': True, 'close_ready': False}
            raw = json.dumps(data).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"accepted":true}')
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    port = int(sys.argv[sys.argv.index('--port') + 1])
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()
