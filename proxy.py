#!/usr/bin/env python3
"""
HTTP reverse proxy using stdlib only.
Routes /streamlit/* → streamlit (:8501), everything else → uvicorn (:8000).
"""
import asyncio
import sys

UVICORN_PORT = 8000
STREAMLIT_PORT = 8501
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080


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


async def forward_request(client_reader, client_writer, target_port, path_override=None):
    try:
        target_reader, target_writer = await asyncio.open_connection("127.0.0.1", target_port)

        # Read full request from client
        request = b""
        while True:
            chunk = await asyncio.wait_for(client_reader.read(65536), timeout=10)
            request += chunk
            if b"\r\n\r\n" in request:
                break
            if not chunk:
                break

        # Parse and possibly rewrite path
        if path_override and request:
            lines = request.split(b"\r\n")
            first = lines[0].decode().split(" ")
            if len(first) >= 2:
                first[1] = path_override
                lines[0] = " ".join(first).encode()
                request = b"\r\n".join(lines)

        target_writer.write(request)
        await target_writer.drain()

        # Read response and forward back
        while True:
            response = await asyncio.wait_for(target_reader.read(65536), timeout=30)
            if not response:
                break
            client_writer.write(response)
            await client_writer.drain()
            if len(response) < 65536:
                break

        target_writer.close()
    except Exception as e:
        print(f"Error forwarding to port {target_port}: {e}")
    finally:
        client_writer.close()


async def handle(client_reader, client_writer):
    try:
        request_line = await asyncio.wait_for(client_reader.readline(), timeout=10)
        if not request_line:
            client_writer.close()
            return

        method, raw_path, version = request_line.decode().split()

        # Read headers
        raw_headers = b""
        while True:
            h = await asyncio.wait_for(client_reader.readline(), timeout=10)
            raw_headers += h
            if h == b"\r\n":
                break

        # Decide target
        if raw_path.startswith("/streamlit"):
            target_port = STREAMLIT_PORT
            path_override = raw_path[len("/streamlit"):] or "/"
        else:
            target_port = UVICORN_PORT
            path_override = None

        await forward_request(client_reader, client_writer, target_port, path_override)

    except Exception:
        client_writer.close()


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", LISTEN_PORT)
    print(f"Proxy listening on {LISTEN_PORT} → uvicorn:{UVICORN_PORT} streamlit:{STREAMLIT_PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
