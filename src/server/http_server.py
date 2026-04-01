"""HTTP server for pyclaude local API and dashboard."""

from __future__ import annotations

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

from server.routes import Router
from server.middleware import (
    Middleware,
    MiddlewareChain,
    AuthMiddleware,
    LoggingMiddleware,
    CorsMiddleware,
)

logger = logging.getLogger(__name__)


class PyclaudeRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler that delegates to the router and middleware chain."""

    server: "PyclaudeHTTPServer"  # type: ignore[assignment]

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default stderr logging; we use our own logger
        pass

    def _get_headers(self) -> Dict[str, str]:
        return {k: v for k, v in self.headers.items()}

    def _read_body(self) -> Optional[bytes]:
        length = self.headers.get("Content-Length")
        if length:
            return self.rfile.read(int(length))
        return None

    def _send_response(self, status: int, headers: Dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        headers = self._get_headers()
        body = self._read_body()

        app = self.server.app

        resolved = app.router.resolve(method, path)
        if resolved is None:
            self._send_response(
                404,
                {"Content-Type": "application/json"},
                json.dumps({"error": "not found", "path": path}).encode(),
            )
            return

        route, params = resolved

        def final_handler() -> Tuple[int, Dict[str, str], bytes]:
            merged_params = {**params, **query}
            return route.handler(path, merged_params, body, headers)

        status, resp_headers, resp_body = app.middleware_chain.execute(
            method, path, headers, body, final_handler
        )
        self._send_response(status, resp_headers, resp_body)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def do_OPTIONS(self) -> None:
        self._handle("OPTIONS")


class PyclaudeHTTPServer(HTTPServer):
    """Extended HTTPServer that holds a reference to the app."""

    def __init__(self, server_address: Tuple[str, int], app: "PyclaudeServer"):
        self.app = app
        super().__init__(server_address, PyclaudeRequestHandler)


class PyclaudeServer:
    """Main server class: configures routes, middleware, and manages lifecycle."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7429,
        auth_token: str = "",
        cors_origins: Optional[List[str]] = None,
    ):
        self.host = host
        self.port = port
        self.router = Router()
        self.middleware_chain = MiddlewareChain()
        self._server: Optional[PyclaudeHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Set up default middleware stack
        self.middleware_chain.use(LoggingMiddleware())
        self.middleware_chain.use(CorsMiddleware(allowed_origins=cors_origins or ["*"]))
        if auth_token:
            self.middleware_chain.use(AuthMiddleware(token=auth_token))

    def add_route(self, method: str, pattern: str, handler: Any, name: str = "") -> None:
        """Add a custom route to the server."""
        self.router.add_route(method, pattern, handler, name)

    def add_middleware(self, middleware: Middleware) -> None:
        """Add custom middleware to the chain."""
        self.middleware_chain.use(middleware)

    def start(self, blocking: bool = False) -> None:
        """Start the HTTP server. If blocking=False, runs in a background thread."""
        if self._running:
            logger.warning("Server already running on %s:%d", self.host, self.port)
            return

        self._server = PyclaudeHTTPServer((self.host, self.port), self)
        self._running = True
        logger.info("Starting server on %s:%d", self.host, self.port)

        if blocking:
            try:
                self._server.serve_forever()
            except KeyboardInterrupt:
                self.stop()
        else:
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="pyclaude-server",
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._server and self._running:
            logger.info("Stopping server on %s:%d", self.host, self.port)
            self._server.shutdown()
            self._running = False
            if self._thread:
                self._thread.join(timeout=5)
                self._thread = None

    def handle_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Programmatic request handling (useful for testing)."""
        hdrs = headers or {}
        resolved = self.router.resolve(method, path)
        if resolved is None:
            return (
                404,
                {"Content-Type": "application/json"},
                json.dumps({"error": "not found"}).encode(),
            )

        route, params = resolved

        def final() -> Tuple[int, Dict[str, str], bytes]:
            return route.handler(path, params, body, hdrs)

        return self.middleware_chain.execute(method, path, hdrs, body, final)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"
