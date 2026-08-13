#!/usr/bin/env python3
"""Reverse TCP bridge so WSL atelier can reach Windows Forge on 127.0.0.1:7862.

Why: Windows Firewall / Hyper-V blocks WSL→Windows:7862 even with --listen.
Windows CAN connect to WSL. So Windows runs as client, WSL as server.

Usage:
  # Terminal A (WSL)
  python scripts/sd_reverse_bridge.py server --listen 127.0.0.1:17862 --control 0.0.0.0:17999

  # Terminal B (Windows)
  python sd_reverse_bridge.py client --server 172.25.159.6:17999 --target 127.0.0.1:7862

  # atelier .env
  SD_WEBUI_URL=http://127.0.0.1:17862
"""

from __future__ import annotations

import argparse
import asyncio
import sys


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
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
            await writer.wait_closed()
        except Exception:
            pass


async def _bidirectional(
    a_reader: asyncio.StreamReader,
    a_writer: asyncio.StreamWriter,
    b_reader: asyncio.StreamReader,
    b_writer: asyncio.StreamWriter,
) -> None:
    """Pipe both directions; close both when either side ends."""
    try:
        await asyncio.gather(
            _pipe(a_reader, b_writer),
            _pipe(b_reader, a_writer),
        )
    except Exception:
        pass
    finally:
        for w in (a_writer, b_writer):
            try:
                w.close()
            except Exception:
                pass


async def run_server(listen_host: str, listen_port: int, control_host: str, control_port: int) -> None:
    """WSL side: accept agent on control_port; expose listen_port to local atelier.

    Protocol:
      - agent maintains one control connection
      - for each incoming local connection, server writes OPEN\\n on control
      - agent opens a data connection to control_port+1 and dials Forge
      - server pairs data channel with the waiting local client
    """
    agent_writer: asyncio.StreamWriter | None = None
    agent_lock = asyncio.Lock()
    waiters: asyncio.Queue[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = asyncio.Queue()
    data_port = control_port + 1

    async def on_data(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            local_reader, local_writer = await asyncio.wait_for(waiters.get(), timeout=30)
        except TimeoutError:
            print("[server] data channel timeout (no waiting local)", flush=True)
            writer.close()
            return
        await _bidirectional(reader, writer, local_reader, local_writer)

    async def on_local(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal agent_writer
        async with agent_lock:
            aw = agent_writer
        if aw is None:
            print("[server] no agent; reject local connection", flush=True)
            writer.close()
            return
        await waiters.put((reader, writer))
        try:
            aw.write(b"OPEN\n")
            await aw.drain()
        except Exception as e:
            print(f"[server] failed to signal agent: {e}", flush=True)
            try:
                writer.close()
            except Exception:
                pass

    async def on_control(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal agent_writer
        peer = writer.get_extra_info("peername")
        print(f"[server] agent control from {peer}", flush=True)
        async with agent_lock:
            old = agent_writer
            agent_writer = writer
        if old is not None and old is not writer:
            try:
                old.close()
            except Exception:
                pass
        try:
            while True:
                try:
                    line = await reader.readline()
                except (ConnectionResetError, ConnectionError, BrokenPipeError):
                    break
                if not line:
                    break
        finally:
            async with agent_lock:
                if agent_writer is writer:
                    agent_writer = None
            print("[server] agent control closed", flush=True)
            try:
                writer.close()
            except Exception:
                pass

    control_srv = await asyncio.start_server(on_control, control_host, control_port)
    data_srv = await asyncio.start_server(on_data, control_host, data_port)
    local_srv = await asyncio.start_server(on_local, listen_host, listen_port)
    print(
        f"[server] local http://{listen_host}:{listen_port}  "
        f"control {control_host}:{control_port}  data {control_host}:{data_port}",
        flush=True,
    )
    async with control_srv, data_srv, local_srv:
        await asyncio.gather(
            control_srv.serve_forever(),
            data_srv.serve_forever(),
            local_srv.serve_forever(),
        )


async def run_client(server: str, target: str) -> None:
    """Windows side: connect control to WSL; on OPEN, dial target and data port."""
    shost, sport = server.rsplit(":", 1)
    sport_i = int(sport)
    data_port = sport_i + 1
    thost, tport = target.rsplit(":", 1)
    tport_i = int(tport)

    while True:
        try:
            print(f"[client] connecting control {shost}:{sport_i} ...", flush=True)
            c_reader, c_writer = await asyncio.open_connection(shost, sport_i)
            print("[client] control up", flush=True)
            try:
                while True:
                    line = await c_reader.readline()
                    if not line:
                        raise ConnectionError("control closed")
                    if line.strip() != b"OPEN":
                        continue

                    async def open_channel() -> None:
                        try:
                            d_reader, d_writer = await asyncio.open_connection(shost, data_port)
                            t_reader, t_writer = await asyncio.open_connection(thost, tport_i)
                        except Exception as e:
                            print(f"[client] open channel failed: {e}", flush=True)
                            return
                        print("[client] channel open", flush=True)
                        await _bidirectional(d_reader, d_writer, t_reader, t_writer)
                        print("[client] channel closed", flush=True)

                    asyncio.create_task(open_channel())
            finally:
                try:
                    c_writer.close()
                    await c_writer.wait_closed()
                except Exception:
                    pass
        except Exception as e:
            print(f"[client] reconnect in 2s ({e})", flush=True)
            await asyncio.sleep(2)


def main() -> None:
    p = argparse.ArgumentParser(description="WSL↔Windows reverse TCP bridge for SD WebUI")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("server", help="Run in WSL")
    s.add_argument("--listen", default="127.0.0.1:17862", help="Local address for atelier")
    s.add_argument("--control", default="0.0.0.0:17999", help="Control listen (Windows connects here)")

    c = sub.add_parser("client", help="Run on Windows")
    c.add_argument("--server", required=True, help="WSL host:control_port e.g. 172.25.159.6:17999")
    c.add_argument("--target", default="127.0.0.1:7862", help="Forge address on Windows")

    args = p.parse_args()
    if args.cmd == "server":
        lh, lp = args.listen.rsplit(":", 1)
        ch, cp = args.control.rsplit(":", 1)
        asyncio.run(run_server(lh, int(lp), ch, int(cp)))
    else:
        asyncio.run(run_client(args.server, args.target))


if __name__ == "__main__":
    main()
