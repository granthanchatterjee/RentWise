"""Small HTTP server (standard library only): JSON API + the demo web page."""
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import listings, search
from .foundation import RES_DIR, NotFound, ValidationError

INDEX = os.path.join(RES_DIR, "web", "index.html")


class Handler(BaseHTTPRequestHandler):
    server_version = "RentWise/0.3"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.command} {self.path}\n")

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ValidationError(["Request body must be valid JSON"])
        if not isinstance(data, dict):
            raise ValidationError(["Request body must be a JSON object"])
        return data

    def _handle(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        m = self.command
        try:
            if m == "GET" and not parts:
                with open(INDEX, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if parts[:1] == ["api"]:
                route = parts[1:2]
                lid = parts[2] if len(parts) > 2 else None
                if route == ["meta"] and m == "GET":
                    return self._send(200, search.filter_options())
                if route == ["listings"]:
                    if lid is None:
                        if m == "GET":
                            query = {k: v[0] for k, v in parse_qs(url.query).items()}
                            return self._send(200, search.search_listings(query))
                        if m == "POST":
                            return self._send(201, listings.create_listing(self._body()))
                    elif lid.isdigit():
                        i = int(lid)
                        if m == "GET":
                            return self._send(200, listings.get_listing(i))
                        if m == "PUT":
                            return self._send(200, listings.update_listing(i, self._body()))
                        if m == "DELETE":
                            listings.delete_listing(i)
                            return self._send(200, {"deleted": i})
            raise NotFound("No such route")
        except ValidationError as e:
            self._send(400, {"errors": e.errors})
        except NotFound as e:
            self._send(404, {"errors": [str(e)]})
        except Exception:
            traceback.print_exc()
            self._send(500, {"errors": ["Server error. Check the terminal for details."]})

    do_GET = do_POST = do_PUT = do_DELETE = _handle


def make_server(port=8000):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
