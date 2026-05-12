#!/usr/bin/env python3
"""
HTTP reverse proxy: forwards requests to uvicorn and streamlit.
Usage: python proxy.py <uvicorn_port> <streamlit_port> <proxy_port>
Routes /streamlit/* to streamlit, everything else to uvicorn.
"""
import asyncio
import sys

UVICORN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
STREAMLIT_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8501
PROXY_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8080


async def pipe(reader, writer):
    try:
        while True:
            data = await asyncio.wait_for(reader.read(65536), timeout=30)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except asyncio.TimeoutError:
        pass
    finally:
        writer.close()


async def handle(client_reader, client_writer):
    try:
        request_line = await asyncio.wait_for(client_reader.readline(), timeout=5)
        if not request_line:
            client_writer.close()
            return

        method, raw_path, version = request_line.decode().split()
        headers = {}
        raw_headers = b""
        while True:
            h = await asyncio.wait_for(client_reader.readline(), timeout=5)
            raw_headers += h
            if h == b"\r\n":
                break
            k, v = h.decode().split(":", 1)
            headers[k.strip().lower()] = v.strip()

        # Determine target
        if raw_path.startswith("/streamlit"):
            target_host = "127.0.0.1"
            target_port = STREAMLIT_PORT
            target_path = raw_path[len("/streamlit") :] or "/"
            new_request = f"{method} {target_path} {version}\r\n".encode() + raw_headers
        else:
            target_host = "127.0.0.1"
            target_port = UVICORN_PORT
            new_request = request_line + raw_headers

        try:
            target_reader, target_writer = await asyncio.open_connection(target_host, target_port)
        except Exception:
            client_writer.close()
            return

        target_writer.write(new_request)
        await target_writer.drain()

        # Read response and forward back to client
        try:
            while True:
                response = await asyncio.wait_for(target_reader.read(65536), timeout=30)
                if not response:
                    break
                client_writer.write(response)
                await client_writer.drain()
                if len(response) < 65536:
                    break
        except asyncio.TimeoutError:
            pass
        finally:
            target_writer.close()
            client_writer.close()

    except Exception:
        client_writer.close()


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", PROXY_PORT)
    print(f"Reverse proxy running on port {PROXY_PORT}", flush=True)
    print(f"  /streamlit/* → streamlit on {STREAMLIT_PORT}", flush=True)
    print(f"  everything else → uvicorn on {UVICORN_PORT}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        print(f"Starting reverse proxy on port {PROXY_PORT}...", flush=True)
        print(f"  /streamlit/* → streamlit on {STREAMLIT_PORT}", flush=True)
        print(f"  everything else → uvicorn on {UVICORN_PORT}", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        asyncio.run(main())
    except Exception as e:
        print(f"ERROR: proxy.py failed to start: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
