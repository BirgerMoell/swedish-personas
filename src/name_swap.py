"""Replace names inside finished persona texts (v2 names -> v3 names), per uuid.

Usage: python3 src/name_swap.py PROSE.jsonl OUT.jsonl [--old SEEDS_OLD.parquet] [--new SEEDS_NEW.parquet]
                                [--flagged FLAGGED.txt] [--report REPORT.json]

For every row the old first and last name are replaced by the new ones in every text field. The match is
case-sensitive, starts at a word boundary and keeps a trailing genitive "s" ("Annas", "Lindqvists").
Rows whose names did not change are copied untouched. The names are the only tokens that change.

Flagged rows: the text reuses a word from the OLD surname (e.g. a Skog- name with a forest hobby). After the
swap that word no longer matches the surname, so these rows are listed for regeneration (or a human look).
Also flagged: the old name is still found after the swap, or the new first name already occurred in the text.
"""

import argparse
import json
import re
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = ("sson", "son", "berg", "ström", "lund", "qvist", "kvist", "gren", "dahl", "holm", "man", "din", "stedt", "ell", "én")


def stem(surname):
    s = surname.lower()
    for suf in SUFFIXES:
        if s.endswith(suf) and len(s) - len(suf) >= 5:
            return s[: -len(suf)]
    return s if len(s) >= 6 else None  # short stems match ordinary words


def walk(value, fn):
    """Apply fn to every string inside nested dicts and lists (the work profile is nested)."""
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [walk(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: walk(v, fn) for k, v in value.items()}
    return value


def strings(row):
    """All text of a row, including nested fields, as (field, text) pairs."""
    for key, value in row.items():
        if key == "uuid":
            continue
        texts = []
        walk(value, lambda t: texts.append(t) or t)
        for t in texts:
            yield key, t


def swap_row(row, old, new):
    """Return (new_row, flags)."""
    mapping = {}
    if old["first_name"] != new["first_name"]:
        mapping[old["first_name"]] = new["first_name"]
    if old["last_name"] != new["last_name"]:
        mapping[old["last_name"]] = new["last_name"]
    flags = []
    if not mapping:
        return row, flags
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)) + r")(s?)(?!\w)")
    out = dict(row)
    before = " ".join(v for _, v in strings(row))
    for key, value in row.items():
        if key != "uuid":
            out[key] = walk(value, lambda t: pattern.sub(lambda m: mapping[m.group(1)] + m.group(2), t))
    after = " ".join(v for _, v in strings(out))
    low_before = before.lower()
    st = stem(old["last_name"])
    if old["last_name"] != new["last_name"] and st and re.search(r"(?<!\w)" + re.escape(st), low_before.replace(old["last_name"].lower(), "")):
        flags.append("surname word reused")
    if old["first_name"] != new["first_name"] and new["first_name"] in before:
        flags.append("new first name already in text")
    for name in mapping:
        if re.search(r"(?<!\w)" + re.escape(name) + r"(s?)(?!\w)", after):
            flags.append(f"old name '{name}' still present")
    return out, flags


def load_names(path):
    t = pq.read_table(path, columns=["uuid", "first_name", "last_name"]).to_pylist()
    return {r["uuid"]: r for r in t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prose")
    ap.add_argument("out")
    ap.add_argument("--old", default=str(ROOT / "data/swedish_personas_100k_seeds.parquet"))
    ap.add_argument("--new", default=str(ROOT / "data/scratch_names/new_100k_seeds.parquet"))
    ap.add_argument("--flagged", default=None)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    old, new = load_names(args.old), load_names(args.new)
    stats = {"rows": 0, "failed_rows_copied": 0, "unchanged": 0, "swapped": 0, "flagged": 0, "flags": {}}
    flagged = []
    with open(args.prose, encoding="utf-8") as src, open(args.out, "w", encoding="utf-8") as dst:
        for line in src:
            row = json.loads(line)
            stats["rows"] += 1
            if "failed" in row or row["uuid"] not in old or row["uuid"] not in new:
                stats["failed_rows_copied"] += 1
                dst.write(line if line.endswith("\n") else line + "\n")
                continue
            out, flags = swap_row(row, old[row["uuid"]], new[row["uuid"]])
            if out is row:
                stats["unchanged"] += 1
            else:
                stats["swapped"] += 1
            if flags:
                stats["flagged"] += 1
                flagged.append(row["uuid"])
                for f in flags:
                    key = re.sub(r"'.*'", "'..'", f)
                    stats["flags"][key] = stats["flags"].get(key, 0) + 1
            dst.write(json.dumps(out, ensure_ascii=False) + "\n")
    if args.flagged:
        Path(args.flagged).write_text("\n".join(flagged) + "\n", encoding="utf-8")
    if args.report:
        Path(args.report).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
