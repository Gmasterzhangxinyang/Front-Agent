#!/usr/bin/env python3
"""HTTP reverse proxy. Routes /streamlit/*, /_stcore/*, /static/* to Streamlit:8500; everything else to Uvicorn:8000."""
import asyncio
import sys

UVICORN_PORT = 8000
STREAMLIT_PORT = 8501
LISTEN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8080


def build_request(method, path, headers, host_override=None):
    """Build a HTTP request byte string."""
    # Parse headers into dict
    header_dict = {}
    for line in headers.decode().splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            header_dict[k] = v
    # Override Host if needed
    if host_override:
        header_dict["Host"] = host_override
    # Rebuild headers string
    rebuilt = "\r\n".join(f"{k}: {v}" for k, v in header_dict.items())
    return f"{method} {path} HTTP/1.1\r\n{rebuilt}\r\n\r\n".encode()


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def handle(client_reader, client_writer):
    try:
        # Read request line
        request_line = await client_reader.readline()
        if not request_line:
            client_writer.close()
            return
        method, path, version = request_line.decode().split()

        # Read headers
        raw_headers = b""
        while True:
            h = await client_reader.readline()
            raw_headers += h
            if h == b"\r\n":
                break

        # Route
        if path.startswith("/streamlit") or path.startswith("/_stcore") or path.startswith("/static"):
            target_port = STREAMLIT_PORT
            clean_path = path[len("/streamlit"):] if path.startswith("/streamlit") else path
            clean_path = clean_path or "/"
            req = build_request(method, clean_path, raw_headers, host_override="localhost:8500")
        else:
            target_port = UVICORN_PORT
            clean_path = path
            req = build_request(method, clean_path, raw_headers)

        # Connect and forward
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", target_port)
        except Exception as e:
            print(f"[proxy] connect to {target_port} failed: {e}", flush=True)
            client_writer.close()
            return

        writer.write(req)
        await writer.drain()

        # Stream response back
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                client_writer.write(data)
                await client_writer.drain()
                if len(data) < 65536:
                    break
        except Exception:
            pass
        finally:
            writer.close()
            client_writer.close()

    except Exception as e:
        print(f"[proxy] error: {e}", flush=True)
        try:
            client_writer.close()
        except:
            pass


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", LISTEN_PORT)
    print(f"[proxy] {LISTEN_PORT} → uvicorn:{UVICORN_PORT} streamlit:{STREAMLIT_PORT}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[proxy] fatal: {e}", flush=True)
        sys.exit(1)
