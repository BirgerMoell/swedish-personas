"""Local first-name factors from SCB's newborn names per county and municipality (2020-2022).

SCB lists a name for a region only when at least three children got it, and groups spellings (Lucas/Lukas).
For each sex and municipality this module gives a factor per name: how much more (or less) often the name
is given there than nationally. Because counts are small it is shrunk toward 1 with an empirical-Bayes rule,
first county against the country, then municipality against its county:

    factor = (observed + TAU) / (expected + TAU)       expected = national share x births x factor above

  births     ASSUMPTION: births in a region are proportional to its population (national births 2020-22 x share).
  observed   the listed count; ASSUMPTION: a name that is not listed has 1 child (it has 0, 1 or 2).
  TAU        prior strength, in children (ASSUMPTION: 4).
Each name's factors are rescaled so that their births-weighted mean is 1, so the national name frequencies
do not change. Factors are clipped to [CLIP_LOW, CLIP_HIGH].

structure.py applies the factor only to Swedish-heritage given names, fully for people born in 2005 or later
and fading to nothing for people born in 1965 or earlier (ASSUMPTION: naming fashions in the 2020s say little
about older generations).
"""

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAU = 4.0
CLIP_LOW, CLIP_HIGH = 0.1, 8.0
SEX = {"M": "1", "K": "2"}  # file code -> sex_code used by structure.py


def weight_exponent(birth_year):
    """1 for people born 2005 or later, 0 for 1965 or earlier, linear in between."""
    return max(0.0, min(1.0, (birth_year - 1965) / 40.0))


class KommunNames:
    def __init__(self):
        population = {}
        county_of = {}
        with (ROOT / "data/scb_municipality_2025.csv").open(encoding="utf-8", newline="") as handle:
            for r in csv.DictReader(handle):
                population[r["municipality_code"]] = float(r["population"])
                county_of[r["municipality_code"]] = r["county_code"]
        listed = defaultdict(float)        # (sex, region code, name) -> children, as listed
        by_name = defaultdict(float)       # (sex, name) -> children in all listed municipalities
        with (ROOT / "data/scb/newborn_names_kommun_2020_2022.csv").open(encoding="utf-8", newline="") as handle:
            for r in csv.DictReader(handle):
                sex, name, code, count = SEX[r["sex"]], r["name"].casefold(), r["region_code"], int(r["count"])
                listed[(sex, code, name)] += count
                if len(code) == 4:
                    by_name[(sex, name)] += count
        births_total = {"1": 158256.0, "2": 148573.0}  # SCB newborns 2020-22 (newborn_names_1998_2022.csv)
        pop_total = sum(population.values())
        births = {(sex, code): births_total[sex] * p / pop_total for code, p in population.items() for sex in births_total}
        county_births = defaultdict(float)
        for (sex, code), b in births.items():
            county_births[(sex, county_of[code])] += b
        names = {(sex, name) for (sex, name) in by_name}
        share = {key: n / births_total[key[0]] for key, n in by_name.items()}   # national share of births
        self.factors, self.fmax = {}, {}
        raw = defaultdict(dict)            # (sex, name) -> {kommun: factor}
        county_f = {}
        for (sex, name) in names:
            for county in {c for c in county_of.values()}:
                expected = share[(sex, name)] * county_births[(sex, county)]
                observed = listed.get((sex, county, name), 1.0)
                county_f[(sex, name, county)] = (observed + TAU) / (expected + TAU)
        for (sex, name) in names:
            for code in population:
                fc = county_f[(sex, name, county_of[code])]
                expected = share[(sex, name)] * births[(sex, code)] * fc
                observed = listed.get((sex, code, name), 1.0)
                raw[(sex, name)][code] = fc * (observed + TAU) / (expected + TAU)
        per_kommun = defaultdict(dict)
        for (sex, name), f in raw.items():
            mean = sum(births[(sex, c)] * v for c, v in f.items()) / sum(births[(sex, c)] for c in f)
            for code, v in f.items():
                per_kommun[(sex, code)][name] = min(CLIP_HIGH, max(CLIP_LOW, v / mean))
        for key, table in per_kommun.items():
            self.factors[key] = table
            self.fmax[key] = max(table.values())

    def factor(self, sex, kommun_code, name):
        return self.factors.get((sex, kommun_code), {}).get(name.casefold(), 1.0)
