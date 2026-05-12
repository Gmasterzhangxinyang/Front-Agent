"""
Simple reverse proxy to route /streamlit/* to Streamlit on 8501
and everything else to uvicorn on PORT
"""
import asyncio
import httpx


async def reverse_proxy(app_port: int, streamlit_port: int = 8501):
    """
    Simple reverse proxy using httpx.
    Listens on port app_port, routes /streamlit/* to streamlit_port, rest to app_port.
    """
    async def handler(reader, writer):
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return

            method, path, version = request_line.decode().split()

            headers = {}
            while True:
                line = await reader.readline()
                if line == b"\r\n":
                    break
                key, value = line.decode().split(":", 1)
                headers[key.strip().lower()] = value.strip()

            # Determine target
            if path.startswith("/streamlit"):
                # Strip /streamlit prefix
                new_path = path[len("/streamlit"):]
                if not new_path:
                    new_path = "/"
                target_host = "localhost"
                target_port = streamlit_port
            else:
                target_host = "localhost"
                target_port = app_port

            # Connect to target
            try:
                reader2, writer2 = await asyncio.open_connection(target_host, target_port)

                if target_port == streamlit_port:
                    # Forward to Streamlit with new path
                    request_line = f"{method} {new_path} {version}\r\n".encode()
                    writer2.write(request_line)
                    # Forward headers (skip host)
                    for k, v in headers.items():
                        if k != "host":
                            writer2.write(f"{k}: {v}\r\n".encode())
                    writer2.write(b"\r\n")
                    # Forward body if present
                    if method in ("POST", "PUT", "PATCH"):
                        content_length = headers.get("content-length", "0")
                        if content_length != "0":
                            body = await reader.readexactly(int(content_length))
                            writer2.write(body)
                    await writer2.drain()
                else:
                    # Proxy to uvicorn - forward original request
                    writer2.write(request_line)
                    for k, v in headers.items():
                        if k != "host":
                            writer2.write(f"{k}: {v}\r\n".encode())
                    writer2.write(b"\r\n")
                    await writer2.drain()

                # Read response
                response_line = await reader2.readline()
                response_headers = b""
                while True:
                    h = await reader2.readline()
                    response_headers += h
                    if h == b"\r\n":
                        break
                body = await reader2.read(4096)

                # Send response back
                writer.write(response_line)
                writer.write(response_headers)
                writer.write(body)
                await writer.drain()

                writer2.close()
            except Exception as e:
                error_resp = b"HTTP/1.1 502 Bad Gateway\r\n\r\n"
                writer.write(error_resp)

            writer.close()

        except Exception as e:
            writer.close()

    server = await asyncio.start_server(handler, "0.0.0.0", 8080)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    asyncio.run(reverse_proxy(port))
