"""Fetch the Statistics Sweden tables behind the v2 structured layer.

Usage: python3 src/fetch_scb_v2.py
Writes one CSV per table to data/scb/ and a manifest (data/scb/source.json).

Names       given names and surnames with at least 10 bearers (2020), mean age per given name (2020), the 100 most
            common given names by birth year (1922-2021), newborn names (1998-2022)
Birthplace  population by county, country of birth and sex (2025);
            population by country of birth, age and sex (2025);
            foreign-born and Swedish-born by parents' birthplace, by county, age and sex (2025)
Education   population 16-95+ by county, level, age and sex (2025)
Occupation  employees by county, SSYK 3-digit, age and sex (2024); by SSYK 4-digit,
            education, age and sex (2024); by SSYK 4-digit, industry, age and sex (2024);
            by SSYK 4-digit, region of birth and sex (2024)
"""

import csv
import json
import subprocess
import time
from datetime import date
from pathlib import Path

API = "https://api.scb.se/OV0104/v1/doris/sv/ssd/"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "scb"
COUNTIES = ["01", "03", "04", "05", "06", "07", "08", "09", "10", "12", "13", "14", "17", "18", "19", "20", "21", "22", "23", "24", "25"]

# name -> (path, {variable: values or "*"}, year or None for "all years in the selection")
TABLES = {
    "given_names_2020": ("BE/BE0001/BE0001G/BE0001TNamn10", {"Tilltalsnamn": "*", "Tid": ["2020"]}),
    "surnames_2020": ("BE/BE0001/BE0001G/BE0001ENamn10", {"Efternamn": "*", "Tid": ["2020"]}),
    "given_names_mean_age_2020": ("BE/BE0001/BE0001G/BE0001T08AR", {"Tilltalsnamn": "*", "Tid": ["2020"]}),
    "given_names_top100_by_birth_year": ("BE/BE0001/BE0001G/BE0001T100", {"Tilltalsnamn": "*", "Tid": "*"}),
    "birth_country_by_county_2025": ("BE/BE0101/BE0101E/FolkmRegFlandKCKM", {"Region": COUNTIES, "Fodelseregion": "*", "Kon": ["1", "2"], "Tid": ["2025"]}),
    "birth_country_by_age_2025": ("BE/BE0101/BE0101E/FodelselandArKCKM", {"Fodelseland": "*", "Alder": ["-4"] + [f"{a}-{a + 4}" for a in range(5, 100, 5)] + ["100+5"], "Kon": ["1", "2"], "Tid": ["2025"]}),
    "education_by_county_age_sex_2025": ("UF/UF0506/UF0506B/UtbBefRegionR", {"Region": COUNTIES, "UtbildningsNiva": "*", "Alder": "*", "Kon": "*", "Tid": ["2025"]}),
    "background_by_county_age_sex_2025": ("BE/BE0101/BE0101Q/UtlSvBakgFinCKM", {"Region": COUNTIES, "UtlBakgrund": ["08", "4", "5", "6"], "Alder": [str(a) for a in range(100)] + ["100+1"], "Kon": ["1", "2"], "Tid": ["2025"]}),
    "occupation3_by_county_age_sex_2024": ("AM/AM0208/AM0208C/YREG55BAS", {"Region": COUNTIES, "Yrke2012": "*", "Alder": "*", "Kon": "*", "Tid": ["2024"]}),
    "occupation4_by_education_age_sex_2024": ("AM/AM0208/AM0208E/YREG51BAS", {"Yrke2012": "*", "UtbNivaSun2020": "*", "Alder": "*", "Kon": "*", "Tid": ["2024"]}),
    "occupation4_by_industry_2024": ("AM/AM0208/AM0208E/YREG54BAS", {"Yrke2012": "*", "SNI2007": "*", "Alder": "*", "Kon": "*", "Tid": ["2024"]}),
    "occupation4_by_birth_region_2024": ("AM/AM0208/AM0208E/YREG53BAS", {"Yrke2012": "*", "Fodelseregion": "*", "Kon": "*", "Tid": ["2024"]}),
}
NEWBORN = "BE/BE0001/BE0001D/BE0001Nyfodda"


def call(path, payload=None):
    """Call the API through curl: urllib stalls on this server until its keep-alive timeout."""
    cmd = ["curl", "-sS", "--fail", "--max-time", "300", "-H", "Content-Type: application/json", API + path]
    if payload is not None:
        cmd += ["--data-binary", json.dumps(payload)]
    for attempt in range(5):
        try:
            raw = subprocess.run(cmd, check=True, capture_output=True).stdout
            return json.loads(raw.decode("utf-8-sig"))
        except Exception as error:  # the API allows 10 calls per 10 seconds
            if attempt == 4:
                raise
            print(f"  retry after {error}", flush=True)
            time.sleep(5 * (attempt + 1))
        finally:
            time.sleep(1.2)


def fetch(path, selection):
    meta = call(path)
    texts = {v["code"]: dict(zip(v["values"], v["valueTexts"])) for v in meta["variables"]}
    query = []
    for code, values in selection.items():
        if values == "*":
            query.append({"code": code, "selection": {"filter": "all", "values": ["*"]}})
        else:
            if code == "Alder":  # age codes differ slightly between tables
                values = [v for v in values if v in texts[code]] or values
            query.append({"code": code, "selection": {"filter": "item", "values": values}})
    result = call(path, {"query": query, "response": {"format": "json"}})
    keys = [c["code"] for c in result["columns"] if c["type"] != "c"]
    header = []
    for k in keys:
        header += [k, k + "_text"]
    rows = []
    for item in result["data"]:
        value = item["values"][0]
        try:
            count = float(value.replace(",", "."))
            count = int(count) if count == int(count) and "." not in value else count
        except ValueError:
            count = 0
        if count <= 0:
            continue
        row = []
        for k, v in zip(keys, item["key"]):
            row += [v, texts[k].get(v, v)]
        rows.append(row + [count])
    return meta["title"], header + ["count"], rows


def save(name, header, rows):
    with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"accessed": date.today().isoformat(), "api": API, "tables": {}}
    if (OUT / "source.json").exists():
        manifest["tables"] = json.loads((OUT / "source.json").read_text(encoding="utf-8"))["tables"]
    for name, (path, selection) in TABLES.items():
        if (OUT / f"{name}.csv").exists():  # resumable: delete a file to fetch it again
            continue
        print(f"fetching {name} ...", flush=True)
        title, header, rows = fetch(path, selection)
        save(name, header, rows)
        manifest["tables"][name] = {"path": path, "title": title, "rows": len(rows), "sum": sum(r[-1] for r in rows)}
        print(f"{name}: {len(rows):,} rows", flush=True)
        (OUT / "source.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # newborn names are too many cells for one call: fetch five years at a time
    header, rows, title = None, [], ""
    years = [str(y) for y in range(1998, 2023)]
    for i in range(0, len(years), 5):
        title, header, part = fetch(NEWBORN, {"Tilltalsnamn": "*", "Kon": "*", "Tid": years[i:i + 5]})
        rows += part
    save("newborn_names_1998_2022", header, rows)
    manifest["tables"]["newborn_names_1998_2022"] = {"path": NEWBORN, "title": title, "rows": len(rows), "sum": sum(r[-1] for r in rows)}
    print(f"newborn_names_1998_2022: {len(rows):,} rows")
    (OUT / "source.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
