"""
Network of the services of a profile. Each service runs in its own sandbox,
with its own loopback, and the student's sandbox reaches it through a Unix
socket in a directory both sandboxes mount:

    student code -> 127.0.0.1:PORT (forward, student's sandbox)
                 -> Unix socket
                 -> 127.0.0.1:PORT (serve, service's sandbox) -> service

The student's code cannot see the service's processes or files: it only
talks to the service through the port.

It runs inside the sandboxes, so it uses only the standard library and is
started with `python -I`.

Usage:

    net.py serve --socket PATH --port PORT [--grace SECONDS] -- COMMAND
    net.py forward --map PORT=PATH [--map ...] -- COMMAND [ARG...]

serve runs the shell command COMMAND, waits for it to accept connections on
PORT and then creates the socket. It stops the command with SIGTERM when its
stdin closes, and with SIGKILL after the grace period.

forward listens on each PORT, connects each client to the socket at PATH and
runs COMMAND. It exits with the exit code of COMMAND.
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
from collections.abc import Callable

#: Interval between attempts to connect to the service while it starts.
POLL = 0.02


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Network of chalk's profile services.")
    sub = parser.add_subparsers(dest="action", required=True)

    serve = sub.add_parser("serve")
    serve.add_argument("--socket", required=True)
    serve.add_argument("--port", required=True, type=int)
    serve.add_argument("--grace", type=float, default=5.0)
    serve.add_argument("command")

    forward = sub.add_parser("forward")
    forward.add_argument("--map", action="append", required=True, dest="maps")
    forward.add_argument("command", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    if args.action == "serve":
        return run_service(args.command, args.socket, args.port, args.grace)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("forward needs a command")
    return run_forwarded(command, [parse_map(m) for m in args.maps])


def parse_map(text: str) -> tuple[int, str]:
    port, sep, path = text.partition("=")
    if not sep or not port.isdigit() or not path:
        raise SystemExit(f"invalid --map {text!r}: expected PORT=PATH")
    return int(port), path


def run_service(command: str, path: str, port: int, grace: float) -> int:
    proc = subprocess.Popen(
        ["/bin/sh", "-c", command], stdin=subprocess.DEVNULL, start_new_session=True
    )
    closed = threading.Event()

    def wait_stdin() -> None:
        sys.stdin.buffer.read()
        closed.set()

    threading.Thread(target=wait_stdin, daemon=True).start()
    try:
        while not can_connect(port):
            if proc.poll() is not None:
                print(f"service exited with code {proc.returncode} before opening port {port}")
                return proc.returncode or 1
            if closed.wait(POLL):
                return 1

        # The socket appears only when it accepts connections: chalk waits
        # for the file.
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path + ".tmp")
        server.listen(64)
        os.rename(path + ".tmp", path)
        serve_forever(server, lambda: socket.create_connection(("localhost", port)))

        while not closed.wait(0.1) and proc.poll() is None:
            pass
    finally:
        stop(proc, grace)
    return proc.returncode or 0


def stop(proc: subprocess.Popen[bytes], grace: float) -> None:
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, None)):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            pass
        try:
            proc.wait(wait)
            return
        except subprocess.TimeoutExpired:
            continue


def run_forwarded(command: list[str], maps: list[tuple[int, str]]) -> int:
    for port, path in maps:
        server = socket.create_server(("127.0.0.1", port), backlog=64)
        serve_forever(server, lambda path=path: _unix(path))
        # Clients that resolve localhost to ::1 first.
        try:
            server6 = socket.create_server(("::1", port), family=socket.AF_INET6, backlog=64)
        except OSError:
            continue
        serve_forever(server6, lambda path=path: _unix(path))
    try:
        return subprocess.call(command)
    except OSError as e:
        print(f"cannot run {command[0]}: {e.strerror}", file=sys.stderr)
        return 127


def can_connect(port: int) -> bool:
    try:
        socket.create_connection(("localhost", port), timeout=1).close()
        return True
    except OSError:
        return False


def serve_forever(server: socket.socket, connect: Callable[[], socket.socket]) -> None:
    """
    Accept clients in a background thread and pipe each one to a new
    connection from connect().
    """

    def accept() -> None:
        while True:
            client, _ = server.accept()
            threading.Thread(target=bridge, args=(client, connect), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()


def bridge(client: socket.socket, connect: Callable[[], socket.socket]) -> None:
    try:
        upstream = connect()
    except OSError:
        client.close()
        return
    done = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
    done.start()
    pipe(client, upstream)
    done.join()
    client.close()
    upstream.close()


def pipe(source: socket.socket, target: socket.socket) -> None:
    try:
        while chunk := source.recv(65536):
            target.sendall(chunk)
    except OSError:
        pass
    try:
        target.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def _unix(path: str) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        raise
    return sock


if __name__ == "__main__":
    code = main()
    # Daemon threads may still block on stdin or accept(), which breaks the
    # interpreter shutdown.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
