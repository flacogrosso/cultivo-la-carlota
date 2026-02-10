import asyncio
import subprocess
import threading
import signal
import sys

STREAMLIT_PORT = 8501
LISTEN_PORT = 5000
streamlit_ready = False

def start_streamlit():
    global streamlit_ready
    proc = subprocess.Popen([
        "streamlit", "run", "app.py",
        "--server.port", str(STREAMLIT_PORT),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
    ])
    proc.wait()
    sys.exit(1)

async def check_streamlit_ready():
    global streamlit_ready
    while True:
        try:
            r, w = await asyncio.open_connection("127.0.0.1", STREAMLIT_PORT)
            w.close()
            await w.wait_closed()
            streamlit_ready = True
            return
        except Exception:
            await asyncio.sleep(1)

async def relay(reader, writer):
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
        try:
            writer.close()
        except Exception:
            pass

LOADING_PAGE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"Connection: close\r\n\r\n"
    b"<html><head><meta http-equiv='refresh' content='3'></head>"
    b"<body style='background:#1A1A1A;color:#FED100;display:flex;"
    b"justify-content:center;align-items:center;height:100vh;font-family:sans-serif'>"
    b"<h2>Cargando GLM App del Cultivador...</h2></body></html>"
)

HEALTH_OK = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 2\r\n"
    b"Connection: close\r\n\r\n"
    b"ok"
)

async def handle_client(client_reader, client_writer):
    try:
        first_line = await asyncio.wait_for(client_reader.readline(), timeout=10)
        if not first_line:
            client_writer.close()
            return

        first_line_str = first_line.decode("utf-8", errors="replace").strip()

        headers_raw = b""
        while True:
            line = await asyncio.wait_for(client_reader.readline(), timeout=10)
            headers_raw += line
            if line == b"\r\n" or line == b"\n" or not line:
                break

        is_health = ("GET / HTTP" in first_line_str or
                     "GET /_stcore/health" in first_line_str)

        if not streamlit_ready:
            if is_health:
                client_writer.write(HEALTH_OK)
            else:
                client_writer.write(LOADING_PAGE)
            await client_writer.drain()
            client_writer.close()
            return

        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", STREAMLIT_PORT), timeout=5
            )
        except Exception:
            if is_health:
                client_writer.write(HEALTH_OK)
            else:
                client_writer.write(LOADING_PAGE)
            await client_writer.drain()
            client_writer.close()
            return

        upstream_writer.write(first_line + headers_raw)
        await upstream_writer.drain()

        await asyncio.gather(
            relay(client_reader, upstream_writer),
            relay(upstream_reader, client_writer),
        )
    except Exception:
        pass
    finally:
        try:
            client_writer.close()
        except Exception:
            pass

async def main():
    asyncio.get_event_loop().run_in_executor(None, start_streamlit)
    asyncio.create_task(check_streamlit_ready())
    server = await asyncio.start_server(handle_client, "0.0.0.0", LISTEN_PORT)
    print(f"TCP proxy on :{LISTEN_PORT} -> Streamlit :{STREAMLIT_PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
