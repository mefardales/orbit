"""Route definitions for the orbit HTTP server."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional, Tuple

# Handler signature: (path, query_params, body, headers) -> (status, headers, body)
HandlerFunc = Callable[
    [str, Dict[str, str], Optional[bytes], Dict[str, str]],
    Tuple[int, Dict[str, str], bytes],
]


@dataclass
class Route:
    """A single route definition."""
    method: str
    pattern: str
    handler: HandlerFunc
    name: str = ""
    description: str = ""
    _compiled: Optional[re.Pattern] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # Convert simple path patterns like /api/{id} to regex
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", self.pattern)
        self._compiled = re.compile(f"^{regex}$")

    def match(self, method: str, path: str) -> Optional[Dict[str, str]]:
        """Check if a request matches this route. Returns path params or None."""
        if method.upper() != self.method.upper():
            return None
        if self._compiled is None:
            return None
        m = self._compiled.match(path)
        if m:
            return m.groupdict()
        return None


class Router:
    """URL router that maps request paths to handler functions."""

    def __init__(self) -> None:
        self._routes: List[Route] = []
        self._start_time = time.time()
        self._request_count = 0
        self._register_defaults()

    def add_route(self, method: str, pattern: str, handler: HandlerFunc, name: str = "") -> None:
        """Register a new route."""
        self._routes.append(Route(
            method=method,
            pattern=pattern,
            handler=handler,
            name=name or f"{method}_{pattern}",
        ))

    def resolve(self, method: str, path: str) -> Optional[Tuple[Route, Dict[str, str]]]:
        """Find the matching route for a request. Returns (route, params) or None."""
        for route in self._routes:
            params = route.match(method, path)
            if params is not None:
                self._request_count += 1
                return route, params
        return None

    def _register_defaults(self) -> None:
        """Register built-in routes for health, status, and metrics."""
        self.add_route("GET", "/health", self._health_handler, "health")
        self.add_route("GET", "/status", self._status_handler, "status")
        self.add_route("GET", "/metrics", self._metrics_handler, "metrics")
        self.add_route("GET", "/routes", self._routes_handler, "routes")

    def _json_response(self, data: Any, status: int = 200) -> Tuple[int, Dict[str, str], bytes]:
        body = json.dumps(data, indent=2).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        return status, headers, body

    def _health_handler(
        self, path: str, params: Dict[str, str],
        body: Optional[bytes], headers: Dict[str, str],
    ) -> Tuple[int, Dict[str, str], bytes]:
        return self._json_response({"status": "healthy", "timestamp": time.time()})

    def _status_handler(
        self, path: str, params: Dict[str, str],
        body: Optional[bytes], headers: Dict[str, str],
    ) -> Tuple[int, Dict[str, str], bytes]:
        uptime = time.time() - self._start_time
        return self._json_response({
            "status": "running",
            "uptime_seconds": round(uptime, 2),
            "request_count": self._request_count,
            "version": "0.1.0",
        })

    def _metrics_handler(
        self, path: str, params: Dict[str, str],
        body: Optional[bytes], headers: Dict[str, str],
    ) -> Tuple[int, Dict[str, str], bytes]:
        uptime = time.time() - self._start_time
        return self._json_response({
            "uptime_seconds": round(uptime, 2),
            "total_requests": self._request_count,
            "route_count": len(self._routes),
            "requests_per_minute": round(self._request_count / max(uptime / 60, 1), 2),
        })

    def _routes_handler(
        self, path: str, params: Dict[str, str],
        body: Optional[bytes], headers: Dict[str, str],
    ) -> Tuple[int, Dict[str, str], bytes]:
        routes_info = [
            {"method": r.method, "pattern": r.pattern, "name": r.name}
            for r in self._routes
        ]
        return self._json_response({"routes": routes_info})
