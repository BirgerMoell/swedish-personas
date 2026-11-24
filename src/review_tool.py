"""A small local tool for reading and reviewing the pilot personas.

Usage:
  python3 src/review_tool.py                 serve on http://127.0.0.1:8765 and open it in the browser
  python3 src/review_tool.py --summary       print the counts from the reviews saved so far

Reads hub_v2/data/pilot.parquet (personas with text and work profile) and
hub_v2/data/task_catalogue.parquet. Every review is appended to data/pilot/reviews.jsonl
as soon as you change it, so nothing is lost if you close the tab. The last line for a
persona wins. The server only listens on this computer.
"""

import argparse
import json
import random
import threading
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PAGE = Path(__file__).with_name("review_tool.html")
lock = threading.Lock()


def load_reviews(path):
    reviews = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                reviews[row["uuid"]] = row
    return reviews


def summary(path):
    reviews = load_reviews(path)
    print(f"{len(reviews)} personas reviewed ({path})")
    print("verdicts:", dict(Counter(r.get("verdict") or "none" for r in reviews.values())))
    print("issues:  ", dict(Counter(i for r in reviews.values() for i in r.get("issues", [])).most_common()))
    print("flagged fields:", dict(Counter(k for r in reviews.values() for k in r.get("flags", {})).most_common()))
    words = Counter(w for r in reviews.values() for w in r.get("words", []))
    print("flagged words and phrases:")
    for word, n in words.most_common():
        print(f"  {n}x  {word}")
    notes = [(r["uuid"][:8], r["note"]) for r in reviews.values() if r.get("note")]
    print(f"{len(notes)} notes")
    for uuid, note in notes:
        print(f"  {uuid}: {note}")


def make_handler(payload, reviews, reviews_path):
    page = PAGE.read_bytes()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, content_type, data):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self.send(200, "text/html; charset=utf-8", page)
            elif self.path == "/api/data":
                with lock:
                    data = json.dumps({**json.loads(body), "reviews": reviews}, ensure_ascii=False).encode("utf-8")
                self.send(200, "application/json; charset=utf-8", data)
            else:
                self.send(404, "text/plain", b"not found")

        def do_POST(self):
            if self.path != "/api/review":
                return self.send(404, "text/plain", b"not found")
            try:
                review = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                if not isinstance(review.get("uuid"), str):
                    raise ValueError("uuid missing")
            except ValueError as error:
                return self.send(400, "text/plain", str(error).encode())
            with lock:
                reviews[review["uuid"]] = review
                reviews_path.parent.mkdir(parents=True, exist_ok=True)
                with reviews_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(review, ensure_ascii=False) + "\n")
            self.send(200, "application/json", b'{"ok":true}')

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "hub_v2/data/pilot.parquet"))
    ap.add_argument("--catalogue", default=str(ROOT / "hub_v2/data/task_catalogue.parquet"))
    ap.add_argument("--reviews", default=str(ROOT / "data/pilot/reviews.jsonl"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    reviews_path = Path(args.reviews)
    if args.summary:
        return summary(reviews_path)
    personas = pq.read_table(args.data).to_pylist()
    random.Random(1).shuffle(personas)  # fixed random order, so the first 30 are a fair sample
    catalogue = {}
    for row in pq.read_table(args.catalogue).to_pylist():
        catalogue.setdefault(row["occupation_code"], {"occupation": row["occupation"], "tasks": []})["tasks"].append(row)
    reviews = load_reviews(reviews_path)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler({"personas": personas, "catalogue": catalogue}, reviews, reviews_path))
    url = f"http://127.0.0.1:{args.port}"
    print(f"{len(personas)} personas, {len(reviews)} already reviewed. Open {url}  (Ctrl+C to stop)", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped; reviews are in", reviews_path)


if __name__ == "__main__":
    main()
