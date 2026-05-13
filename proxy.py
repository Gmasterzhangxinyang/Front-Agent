#!/usr/bin/env python3
"""Minimal threaded HTTP proxy using socketserver."""
import socketserver
import http.client
import sys
import threading

UVICORN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
STREAMLIT_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8501
LISTEN_PORT = UVICORN_PORT  # proxy binds to same port as uvicorn — proxy must start first or uvicorn must --reload


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            # Read full HTTP request
            data = self.request.recv(4096)
            if not data:
                return

            # Parse request line
            lines = data.decode().split("\r\n")
            method, path, version = lines[0].split()

            # Route
            if path.startswith("/streamlit") or path.startswith("/_stcore") or path.startswith("/static"):
                target_port = STREAMLIT_PORT
                clean_path = path[len("/streamlit"):] if path.startswith("/streamlit") else path
                clean_path = clean_path or "/"
            else:
                target_port = UVICORN_PORT
                clean_path = path

            # Connect to target and forward
            target = http.client.HTTPConnection("127.0.0.1", target_port, timeout=15)
            try:
                target.connect()
                target.sock.sendall(data)
                # Read response and forward back
                while True:
                    chunk = target.sock.recv(4096)
                    if not chunk:
                        break
                    self.request.sendall(chunk)
            except Exception as e:
                print(f"[proxy] fwd error: {e}", flush=True)
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
