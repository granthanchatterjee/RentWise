"""Start RentWise:  python run.py   (then open http://127.0.0.1:8000/)"""
import argparse
import threading
import webbrowser

from rentwise.foundation import init_db
from rentwise.seed import seed_if_empty
from rentwise.server import make_server


def main():
    ap = argparse.ArgumentParser(description="RentWise Phase 2 + 3 demo")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    init_db()
    loaded = seed_if_empty()
    if loaded:
        print(f"Loaded {loaded} sample listings")
    server = make_server(args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"RentWise is running at {url}  (press Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
