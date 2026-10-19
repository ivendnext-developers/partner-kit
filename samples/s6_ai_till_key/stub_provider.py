"""S6 — a local stand-in for an AI service: speaks the chat-completions request, answers from providers.stub, needs no
account and no network. For the sample and its tests only. Env: PP_STUB_PORT (default 8127), PP_STUB_DELAY (seconds
to wait before answering). Test markers in the prompt, so a test can make one request slow or failing without
restarting anything: a store named "PP-SLOW-TEST" makes the answer take 5 s; "PP-FAIL-TEST" makes it a server error."""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import providers  # noqa: E402


def make_server(port=0, delay=0.0):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            prompt = req["messages"][-1]["content"]
            time.sleep(delay + (5 if "PP-SLOW-TEST" in prompt else 0))
            if "PP-FAIL-TEST" in prompt:
                self.send_response(500)
                self.end_headers()
                return
            text = providers.stub(prompt)
            data = json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    return ThreadingHTTPServer(("127.0.0.1", port), H)


if __name__ == "__main__":
    s = make_server(int(os.environ.get("PP_STUB_PORT", "8127")), float(os.environ.get("PP_STUB_DELAY", "0")))
    print("stub AI service on", s.server_address, flush=True)
    s.serve_forever()
