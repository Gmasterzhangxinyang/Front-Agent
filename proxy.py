#!/usr/bin/env python3
"""Simple HTTP proxy. Routes /streamlit/* to streamlit:8500, everything else to uvicorn:8080."""
import socketserver
import http.client
import sys

UVICORN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
STREAMLIT_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8501
LISTEN_PORT = UVICORN_PORT  # proxy listens on uvicorn's port (uvicorn starts first on that port, this is a race — not ideal)


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            data = self.request.recv(4096)
            if not data:
                return
            method, path, version = data.decode().split("\r\n")[0].split()

            if path.startswith("/streamlit") or path.startswith("/_stcore") or path.startswith("/static"):
                target_port = STREAMLIT_PORT
                clean_path = path[len("/streamlit"):] if path.startswith("/streamlit") else path
                clean_path = clean_path or "/"
            else:
                target_port = UVICORN_PORT
                clean_path = path

            target = http.client.HTTPConnection("127.0.0.1", target_port, timeout=15)
            try:
                target.connect()
                target.sock.sendall(data)
                while True:
                    chunk = target.sock.recv(4096)
                    if not chunk:
                        break
                    self.request.sendall(chunk)
            finally:
                target.close()
        except Exception as e:
            print(f"[proxy] error: {e}", flush=True)
        finally:
            try:
                self.request.close()
            except:
                pass


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print(f"[proxy] {LISTEN_PORT} → uvicorn:{UVICORN_PORT} streamlit:{STREAMLIT_PORT}", flush=True)
    server = ThreadedTCPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    server.serve_forever()
