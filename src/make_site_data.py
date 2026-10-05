"""Export a small public preview and aggregate charts for GitHub Pages."""

import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
rows = pq.read_table(ROOT / "data/swedish_personas_100k.parquet").to_pylist()
docs = ROOT / "docs"

preview = []
for low, high in ((0, 17), (18, 29), (30, 49), (50, 69), (70, 120)):
    group = [r for r in rows if low <= r["age"] <= high]
    preview.extend(group[:2])
(docs / "sample.json").write_text(json.dumps(preview, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

age_bins = ("0–17", "18–29", "30–49", "50–69", "70+")
def age_bin(age):
    return age_bins[0] if age < 18 else age_bins[1] if age < 30 else age_bins[2] if age < 50 else age_bins[3] if age < 70 else age_bins[4]

stats = {
    "rows": len(rows), "counties": len(set(r["county_code"] for r in rows)),
    "municipalities": len(set(r["municipality_code"] for r in rows)),
    "age_bins": dict(Counter(age_bin(r["age"]) for r in rows)),
    "sex": dict(Counter(r["scb_sex"] for r in rows)),
    "top_counties": Counter(r["county"] for r in rows).most_common(8),
}
(docs / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Wrote site preview and aggregate statistics")
