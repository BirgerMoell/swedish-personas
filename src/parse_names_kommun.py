"""Turn SCB's newborn-name Excel files (per county and municipality, 2020-2022) into one long CSV.

Usage: python3 src/parse_names_kommun.py
Reads data/scb_names_kommun/be0001namntab50-<year>.xlsx, writes data/scb/newborn_names_kommun_2020_2022.csv
with columns year, sex (K/M), name, region_code (2 digits = county, 4 digits = municipality), region, count.
SCB only lists a name for a region when at least three children got it, so missing means 0-2.
"""

import csv
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/scb_names_kommun"
SHEETS = {"Flickor – Girls": "K", "Pojkar – Boys": "M"}


def main():
    out = ROOT / "data/scb/newborn_names_kommun_2020_2022.csv"
    total = 0
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["year", "sex", "name", "region_code", "region", "count"])
        for year in (2020, 2021, 2022):
            book = openpyxl.load_workbook(SRC / f"be0001namntab50-{year}.xlsx", read_only=True)
            for sheet, sex in SHEETS.items():
                rows = list(book[sheet].iter_rows(values_only=True))
                head = next(i for i, r in enumerate(rows) if r[1] and str(r[1]).strip() == "Kod Code")
                regions, codes = rows[head - 1], rows[head + 1]
                columns = [(c, str(codes[c]).strip(), str(regions[c]).strip()) for c in range(1, len(codes)) if codes[c] and str(codes[c]).strip().isdigit()]
                for row in rows[head + 2:]:
                    name = (row[0] or "").strip()
                    if not name or row[1] is None:
                        continue
                    for c, code, region in columns:
                        value = row[c]
                        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
                            writer.writerow([year, sex, name.title(), code, region, int(value)])
                            total += 1
            print(year, "done", flush=True)
    print(total, "rows ->", out)


if __name__ == "__main__":
    main()
