#!/usr/bin/env python3
"""Replay script.json against one candidate and print the transcript as JSON.

usage: run_transcript.py <candidate_dir> <wsgi|http>
Runs in its own process so each candidate imports only its own `pocketcart`.
"""

from __future__ import annotations

import io
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

HERE = Path(__file__).resolve().parent


def via_wsgi(app, step):
    payload = step["raw"].encode() if "raw" in step else (
        json.dumps(step["body"]).encode() if "body" in step else b"")
    environ = {
        "REQUEST_METHOD": step["method"], "PATH_INFO": step["path"],
        "CONTENT_LENGTH": str(len(payload)), "wsgi.input": io.BytesIO(payload),
    }
    for name, value in step.get("headers", {}).items():
        environ["HTTP_" + name.upper().replace("-", "_")] = value
    seen = {}
    raw = b"".join(app(environ, lambda status, headers: seen.update(status=int(status.split()[0]))))
    return seen["status"], raw.decode()


def via_http(base, step):
    payload = step["raw"].encode() if "raw" in step else (
        json.dumps(step["body"]).encode() if "body" in step else None)
    request = urllib.request.Request(
        base + step["path"], data=payload, method=step["method"],
        headers={"Content-Type": "application/json", **step.get("headers", {})},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


class _Quiet(WSGIRequestHandler):
    def log_message(self, *args):  # keep transcripts free of access-log noise
        pass


def main() -> None:
    candidate, transport = Path(sys.argv[1]).resolve(), sys.argv[2]
    sys.path.insert(0, str(candidate / "src"))
    from pocketcart import create_app

    steps = json.loads((HERE / "script.json").read_text())
    app = create_app()
    server = None
    if transport == "http":
        server = make_server("127.0.0.1", 0, app, handler_class=_Quiet)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
    out = []
    for step in steps:
        status, body = via_http(base, step) if server else via_wsgi(app, step)
        out.append({"request": step, "status": status, "body": body})
    if server:
        server.shutdown()
    print(json.dumps(out, sort_keys=True, indent=1))


if __name__ == "__main__":
    main()
