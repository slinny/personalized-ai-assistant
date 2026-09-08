"""Loopback-only HTTP test server; no provider network access."""

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from threading import Thread
from time import monotonic, sleep

import uvicorn
from fastapi import FastAPI


@contextmanager
def serve(app: FastAPI) -> Iterator[HTTPConnection]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        config = uvicorn.Config(app, log_level="error", lifespan="on", timeout_graceful_shutdown=3)
        server = uvicorn.Server(config)
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            deadline = monotonic() + 5
            while not server.started:
                if not thread.is_alive() or monotonic() > deadline:
                    raise AssertionError("Local server did not start")
                sleep(0.01)
            yield connection
        finally:
            connection.close()
            server.should_exit = True
            thread.join(5)
            assert not thread.is_alive(), "Local server did not shut down"
