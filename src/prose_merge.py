"""Merge model-written texts into the structured release, for the same uuids.

Usage: python3 src/prose_merge.py PROSE.jsonl OUT.parquet [--data data/swedish_personas_100k.parquet]

Writes OUT.parquet plus the matching _seeds and _conditions tables, so that
src/metrics.py can score the result exactly like a full release.
"""

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prose")
    ap.add_argument("out")
    ap.add_argument("--data", default=str(ROOT / "data/swedish_personas_100k.parquet"))
    args = ap.parse_args()
    prose = {}
    for line in open(args.prose, encoding="utf-8"):
        row = json.loads(line)
        if "failed" not in row:
            prose[row["uuid"]] = row
    data, out = Path(args.data), Path(args.out)
    table = pq.read_table(data)
    rows = [r for r in table.to_pylist() if r["uuid"] in prose]
    for r in rows:
        # list columns are stored as Python-literal strings, as in Nemotron-Personas
        r.update({k: str(v) if isinstance(v, list) else v for k, v in prose[r["uuid"]].items() if k in table.schema.names})
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), out)
    for suffix in ("_seeds", "_conditions"):
        side = pq.read_table(data.with_name(data.stem + suffix + ".parquet"))
        keep = pa.array([u in prose for u in side.column("uuid").to_pylist()])
        pq.write_table(side.filter(keep), out.with_name(out.stem + suffix + ".parquet"))
    print(f"{len(rows)} personas -> {out}")


if __name__ == "__main__":
    main()
