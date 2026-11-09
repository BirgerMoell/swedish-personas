"""Export a small public preview and aggregate statistics for the GitHub Pages site."""

import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
docs = ROOT / "docs"
rows = pq.read_table(ROOT / "data/swedish_personas_100k.parquet").to_pylist()
conditions = pq.read_table(ROOT / "data/swedish_personas_100k_conditions.parquet").to_pylist()

# Preview: three personas per life stage, in a fixed order.
preview = []
for low, high in ((0, 12), (13, 24), (25, 39), (40, 54), (55, 69), (70, 120)):
    preview.extend([r for r in rows if low <= r["age"] <= high][:3])
(docs / "sample.json").write_text(json.dumps(preview, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

# Population pyramid: five-year bands by sex.
bands = [f"{a}–{a + 4}" for a in range(0, 85, 5)] + ["85+"]
def band(age):
    return min(age // 5, 17)
pyramid = [{"band": b, "Man": 0, "Kvinna": 0} for b in bands]
for r in rows:
    pyramid[band(r["age"])][r["sex"]] += 1

# Share of personas with a condition, by ten-year age band and sex.
def decade(age):
    return min(age // 10, 9)
denominator = Counter((decade(r["age"]), r["sex"]) for r in rows)
sex_by_uuid = {r["uuid"]: (decade(r["age"]), r["sex"]) for r in rows}
counts = Counter((c["condition"], *sex_by_uuid[c["uuid"]]) for c in conditions)
totals = Counter(c["condition"] for c in conditions)
featured = ("högt blodtryck", "astma", "allergi", "depression", "svår oro och ångest", "fetma", "ADHD", "förmaksflimmer", "demenssjukdom", "knäartros", "kranskärlssjukdom", "stroke")
health = {}
for name in featured:
    health[name] = {sex: [round(100 * counts[(name, d, sex)] / denominator[(d, sex)], 2) if denominator[(d, sex)] else None for d in range(10)] for sex in ("Man", "Kvinna")}

stats = {
    "rows": len(rows), "columns": len(rows[0]),
    "counties": len(set(r["lan"] for r in rows)), "municipalities": len(set(r["kommun"] for r in rows)),
    "pyramid": pyramid,
    "sex": dict(Counter(r["sex"] for r in rows)),
    "top_counties": Counter(r["lan"] for r in rows).most_common(8),
    "condition_rows": len(conditions),
    "conditions_total": dict(totals.most_common(12)),
    "health": health,
    "decades": [f"{d * 10}–{d * 10 + 9}" if d < 9 else "90+" for d in range(10)],
}
(docs / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("Wrote site preview and aggregate statistics")
