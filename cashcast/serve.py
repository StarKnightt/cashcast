"""Local mode: serve the web app and score your own CSV on this computer.

Run: python -m cashcast.serve [--port 8765]
Nothing is uploaded anywhere: the browser sends the file to this local process only.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from . import data, features, forecast

WEB = Path(__file__).resolve().parent.parent / "web"
MAX_BYTES = 5_000_000


class Handler(SimpleHTTPRequestHandler):
    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if urlparse(self.path).path == "/api/health":
            return self._json(200, {"local": True})
        return super().do_GET()

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/api/score":
            return self._json(404, {"error": "Not found"})
        size = int(self.headers.get("Content-Length", 0))
        if size <= 0 or size > MAX_BYTES:
            return self._json(400, {"error": "Send a CSV under 5 MB."})
        text = self.rfile.read(size).decode("utf-8-sig", errors="replace")
        as_of_raw = parse_qs(url.query).get("as_of", [""])[0]
        try:
            as_of = pd.Timestamp(as_of_raw) if as_of_raw else pd.Timestamp.today().normalize()
            t0 = time.perf_counter()
            f = features.build(data.load_csv(io.StringIO(text)))
            snap = forecast.score(f, features.matrix(f), as_of)
            snap["seconds"] = round(time.perf_counter() - t0, 1)
            return self._json(200, snap)
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:  # keep the server alive and say what went wrong
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description="Cashcast local mode")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), partial(Handler, directory=str(WEB)))
    url = f"http://localhost:{a.port}/"
    print(f"Cashcast local mode: {url}  (Ctrl+C to stop)")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
