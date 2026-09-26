"""Run the API locally: python -m pocketcart [--port 8000]."""

from __future__ import annotations

import argparse
from wsgiref.simple_server import make_server

from . import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="pocketcart")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with make_server(args.host, args.port, create_app()) as server:
        print(f"PocketCart listening on http://{args.host}:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
