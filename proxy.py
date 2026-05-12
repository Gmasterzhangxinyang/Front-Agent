#!/usr/bin/env python3
import asyncio
import sys

UVICORN_PORT = 8000
STREAMLIT_PORT = 8501
LISTEN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8080

async def handle_client(client_reader, client_writer):
    try:
        # Read request line
        request_line = await client_reader.readline()
        if not request_line:
            client_writer.close()
            return
        
        # Parse request
        parts = request_line.decode().split()
        if len(parts) < 2:
            client_writer.close()
            return
        
        method = parts[0]
        path = parts[1]
        
        # Read headers until blank line
        headers = b""
        while True:
            line = await client_reader.readline()
            headers += line
            if line == b"\r\n":
                break
        
        # Determine target
        # Streamlit's internal assets: /_stcore/*, /static/*
        if path.startswith("/streamlit") or path.startswith("/_stcore") or path.startswith("/static"):
            target_port = STREAMLIT_PORT
            new_path = path[len("/streamlit"):] if path.startswith("/streamlit") else path
            new_path = new_path or "/"
            new_request = f"{method} {new_path} HTTP/1.1\r\n".encode() + headers
        else:
            target_port = UVICORN_PORT
            new_request = request_line + headers
        
        # Connect to target
        try:
            target_reader, target_writer = await asyncio.open_connection("127.0.0.1", target_port)
        except Exception as e:
            print(f"[proxy] Failed to connect to port {target_port}: {e}", flush=True)
            client_writer.close()
            return
        
        # Forward request
        target_writer.write(new_request)
        await target_writer.drain()
        
        # Forward response
        while True:
            data = await target_reader.read(4096)
            if not data:
                break
            client_writer.write(data)
            await client_writer.drain()
        
        target_writer.close()
        client_writer.close()
    except Exception as e:
        print(f"[proxy] Error handling client: {e}", flush=True)
        try:
            client_writer.close()
        except:
            pass

async def main():
    try:
        print(f"[proxy] Starting on port {LISTEN_PORT}", flush=True)
        server = await asyncio.start_server(handle_client, "0.0.0.0", LISTEN_PORT)
        print(f"[proxy] Listening on {LISTEN_PORT}", flush=True)
        print(f"[proxy]   /streamlit/* /_stcore/* /static/* → streamlit:{STREAMLIT_PORT}", flush=True)
        print(f"[proxy]   /* → uvicorn:{UVICORN_PORT}", flush=True)
        async with server:
            await server.serve_forever()
    except Exception as e:
        print(f"[proxy] FATAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[proxy] Shutting down", flush=True)
    except Exception as e:
        print(f"[proxy] Startup failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
