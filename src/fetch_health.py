"""Download national age x sex health rates from Socialstyrelsen and Folkhälsomyndigheten.

Writes data/health_socialstyrelsen.csv, data/health_folkhalsomyndigheten.csv and
data/health_source.json. Both sources are open Swedish public statistics.
"""

import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
YEAR = 2024

SOS = "https://sdb.socialstyrelsen.se/api/v1/sv/diagnoserislutenoppenvard"
FOHM = "https://fohm-app.folkhalsomyndigheten.se/Folkhalsodata/api/v1/sv/A_Folkhalsodata/B_HLV"

# ICD-10-SE three-character codes: annual patients in inpatient and/or specialised outpatient care per 100,000.
SOS_CODES = (
    "I25", "I21", "I48", "I50", "I63", "I73", "J44", "J45", "F00", "F03", "G30", "G20", "G35", "G40", "G43",
    "C50", "C61", "C18", "C34", "C43", "M17", "M16", "M81", "M05", "M06", "H25", "N40", "N18", "F20", "F31",
    "F32", "F41", "F84", "F90", "E10", "K21", "K50", "K51", "K80", "L20", "L40", "H66", "J35", "N20",
)
# Folkhälsomyndigheten national public health survey (self-reported), people aged 16+.
FOHM_TABLES = (
    ("bFyshals/bbdFyshalsovrigt/hlv1sjuaald.px", ("Allergi", "Astma", "Diabetes", "Eksem", "Huvudvärk", "Högt blodtryck", "Inkontinens", "Magtarmbesvär", "Tinnitus", "Yrsel")),
    ("bFyshals/bbbFyshalsbesvar/hlv1roraald.px", ("Svår värk i rygg mm", "Svår värk i rörelseorganen")),
    ("bFyshals/bbeFyshalsvikt/hlv1bmiaald.px", ("Obesitas (BMI 30,0 eller högre)",)),
    ("dPsykhals/hlv1psyaald.px", ("Svår ängslan, oro eller ångest", "Diagnosen depression av läkare", "Svåra sömnbesvär")),
)


def get(url, body=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_sos():
    labels = {row["id"]: row["text"] for row in get(f"{SOS}/diagnos")}
    age_labels = {row["id"]: row["text"] for row in get(f"{SOS}/alder") if row["id"] <= 18}
    rows, missing = [], []
    for code in SOS_CODES:
        if code not in labels:
            missing.append(code)
            continue
        query = urllib.parse.urlencode({"diagnos": code, "ar": YEAR, "region": 0, "matt": 7})
        for item in get(f"{SOS}/resultat?{query}")["data"]:
            if item["konId"] in (1, 2) and item["alderId"] in age_labels:
                value = item["varde"].replace("\xa0", "").replace(" ", "").replace(",", ".")
                rows.append({
                    "icd10": code, "label": labels[code], "age_band": age_labels[item["alderId"]],
                    "sex": "Man" if item["konId"] == 1 else "Kvinna",
                    "patients_per_100k": float(value) if value not in ("", "..", "-") else 0.0, "year": YEAR,
                })
    return rows, missing


def fetch_fohm():
    rows = []
    for table, wanted in FOHM_TABLES:
        meta = get(f"{FOHM}/{table}")
        variables = {v["code"]: dict(zip(v["valueTexts"], v["values"])) for v in meta["variables"]}
        condition_var = meta["variables"][0]["code"]
        age_var = next(v["code"] for v in meta["variables"] if v["code"] == "Ålder")
        age_codes = {text: code for text, code in variables[age_var].items() if text in ("16-29 år", "30-44 år", "45-64 år", "65-84 år", "85- år")}
        query = {"query": [
            {"code": condition_var, "selection": {"filter": "item", "values": [variables[condition_var][w] for w in wanted]}},
            {"code": "Andel och konfidensintervall", "selection": {"filter": "item", "values": ["01"]}},
            {"code": age_var, "selection": {"filter": "item", "values": list(age_codes.values())}},
            {"code": "Kön", "selection": {"filter": "item", "values": ["01", "02"]}},
            {"code": "År", "selection": {"filter": "item", "values": [str(YEAR)]}},
        ], "response": {"format": "json"}}
        condition_names = {code: text for text, code in variables[condition_var].items()}
        age_names = {code: text for text, code in age_codes.items()}
        for item in get(f"{FOHM}/{table}", query)["data"]:
            cond, _, age, sex, _ = item["key"]
            value = item["values"][0]
            if value in ("..", "", None):
                continue
            rows.append({
                "condition": condition_names[cond], "age_band": age_names[age].replace(" år", ""),
                "sex": "Kvinna" if sex == "01" else "Man", "percent": float(value), "year": YEAR,
            })
    return rows


def write(name, rows):
    with (DATA / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    sos_rows, missing = fetch_sos()
    fohm_rows = fetch_fohm()
    write("health_socialstyrelsen.csv", sos_rows)
    write("health_folkhalsomyndigheten.csv", fohm_rows)
    (DATA / "health_source.json").write_text(json.dumps({
        "retrieved": date.today().isoformat(), "year": YEAR,
        "socialstyrelsen": {
            "table": "Diagnoser i sluten och/eller specialiserad öppen vård, årsuppgifter",
            "url": "https://sdb.socialstyrelsen.se/if_dia_sluten_oppen/", "api": SOS,
            "measure": "Antal patienter per 100 000 invånare, riket, by 5-year age band and sex",
            "codes_not_found": missing,
        },
        "folkhalsomyndigheten": {
            "table": "Nationella folkhälsoenkäten (Hälsa på lika villkor), självrapporterat, andel i procent, ålder 16+",
            "url": "https://fohm-app.folkhalsomyndigheten.se/Folkhalsodata/pxweb/sv/A_Folkhalsodata/A_Folkhalsodata__B_HLV/", "api": FOHM,
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Socialstyrelsen rows: {len(sos_rows)}, Folkhälsomyndigheten rows: {len(fohm_rows)}", file=sys.stderr)
    if missing:
        print(f"Codes not found: {missing}", file=sys.stderr)
