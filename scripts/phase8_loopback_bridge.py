"""Temporary loopback-only TCP bridge into the isolated Phase 8 API container.

This uses docker exec over the local daemon rather than attaching API to an
egress-capable Docker network. Stop the bridge after browser/MCP acceptance.
"""
from __future__ import annotations

import os
import socket
import socketserver
import subprocess
import threading


CONTAINER = "private-documents-phase8-api-1"
PROJECT = "private-documents-phase8"
INNER = """import os,socket,threading
s=socket.create_connection(('127.0.0.1',8077),timeout=10)
s.settimeout(None)
def upload():
    try:
        while data:=os.read(0,65536): s.sendall(data)
    finally:
        try:s.shutdown(socket.SHUT_WR)
        except OSError:pass
threading.Thread(target=upload,daemon=True).start()
try:
    while data:=s.recv(65536): os.write(1,data)
finally:s.close()
"""


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        child = subprocess.Popen(["docker", "exec", "-i", CONTAINER, "python", "-c", INNER],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, bufsize=0)
        assert child.stdin is not None and child.stdout is not None

        def upload() -> None:
            try:
                while data := self.request.recv(65536):
                    child.stdin.write(data)
            except (OSError, BrokenPipeError):
                pass
            finally:
                child.stdin.close()

        sender = threading.Thread(target=upload, daemon=True)
        sender.start()
        try:
            while data := os.read(child.stdout.fileno(), 65536):
                self.request.sendall(data)
        except OSError:
            pass
        finally:
            try:
                self.request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            child.terminate()
            child.wait(timeout=10)
            sender.join(timeout=1)


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    label = subprocess.check_output(["docker", "inspect", "--format",
        '{{index .Config.Labels "com.docker.compose.project"}}', CONTAINER], text=True).strip()
    if label != PROJECT:
        raise RuntimeError("Refusing to bridge another project's container")
    with Server(("127.0.0.1", 8078), Handler) as server:
        print("Phase 8 isolated API bridge listening on 127.0.0.1:8078", flush=True)
        server.serve_forever(poll_interval=.5)


if __name__ == "__main__":
    main()
