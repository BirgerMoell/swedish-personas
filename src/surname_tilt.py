"""Regional tilt for Swedish surnames (north-south), calibrated on SCB's landsdel table.

SCB publishes no surname table per kommun. What exists is (data/scb/surname_landsdel_2021.csv, from SCB's
article "Efternamn som slutar på -son klart vanligast") the 25 surnames among the 100 most common that differ
most between Götaland, Svealand and Norrland, as bearers per 1,000 inhabitants. This module turns it into
a region factor for every Swedish surname:

  1. The 25 listed names get their measured factor: the regional rate divided by the national rate.
  2. ASSUMPTION: other names built like them follow the same direction, with half the strength (on a log
     scale): north-leaning nature compounds (Mark-, Sjö-, Hägg-, Näs-, Sund-, -lund, -ström, -qvist ...). The
     southern patronymics (Berntsson, Börjesson, Andreasson) are NOT generalised: other -sson names do not lean
     south (Eriksson is a northern name), so they keep factor 1.
  3. Every other name has factor 1.
  4. Factors are rescaled per name so that the population-weighted mean is 1, and the names without a factor
     absorb the rest within each region, so every tilted name keeps exactly its measured regional factor and its
     national frequency.

The tilt is three regions deep: every county in a landsdel gets the same factor.
"""

import csv
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANDSDEL = {"G": "Götaland", "S": "Svealand", "N": "Norrland"}
COUNTY_LANDSDEL = {
    **dict.fromkeys(("05", "06", "07", "08", "09", "10", "12", "13", "14"), "G"),
    **dict.fromkeys(("01", "03", "04", "17", "18", "19", "20"), "S"),
    **dict.fromkeys(("21", "22", "23", "24", "25"), "N"),
}
# ASSUMPTION: how far unlisted look-alikes follow the listed names (0 = not at all, 1 = fully).
DAMPING = 0.5
NATURE_NORTH = re.compile(r"^(?!.*sson$)(\w*(lund|ström|qvist|kvist|mark)|(mark|sjö|hägg|näs|sund|brän|bys)\w+)$", re.I)


def landsdel_population():
    """Residents per landsdel (2025), only used as weights."""
    pop = dict.fromkeys(LANDSDEL, 0.0)
    path = ROOT / "data/scb_county_age_sex_marital_2025.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            pop[COUNTY_LANDSDEL[r["county_code"]]] += float(r["population"])
    return pop


class SurnameTilt:
    def __init__(self):
        self.pop = landsdel_population()
        total = sum(self.pop.values())
        self.share = {k: v / total for k, v in self.pop.items()}
        self.measured = {}   # name -> {G, S, N: factor}
        with (ROOT / "data/scb/surname_landsdel_2021.csv").open(encoding="utf-8", newline="") as handle:
            for r in csv.DictReader(handle):
                rates = {"G": float(r["per1000_gotaland"]), "S": float(r["per1000_svealand"]), "N": float(r["per1000_norrland"])}
                rates = {k: max(v, 0.05) for k, v in rates.items()}  # the table rounds to 0.1
                mean = sum(self.share[k] * rates[k] for k in rates)
                self.measured[r["name"].casefold()] = {k: v / mean for k, v in rates.items()}
        # direction and strength of the two look-alike classes, from the measured names
        self.north = self._class_log([n for n in self.measured if NATURE_NORTH.search(n)])

    def _class_log(self, names):
        """Mean log factor per landsdel of the measured names in a class."""
        if not names:
            return {k: 0.0 for k in LANDSDEL}
        return {k: sum(math.log(self.measured[n][k]) for n in names) / len(names) for k in LANDSDEL}

    def factors(self, name):
        key = name.casefold()
        if key in self.measured:
            return self.measured[key]
        if not NATURE_NORTH.search(key):
            return {k: 1.0 for k in LANDSDEL}
        logs = self.north
        raw = {k: math.exp(DAMPING * logs[k]) for k in LANDSDEL}
        mean = sum(self.share[k] * raw[k] for k in raw)
        return {k: v / mean for k, v in raw.items()}

    def tilt(self, counts):
        """counts: {surname: bearers}. Returns {landsdel: {surname: weight}}."""
        out = {k: {} for k in LANDSDEL}
        total = sum(counts.values())
        tilted = {name: self.factors(name) for name in counts}
        tilted = {name: f for name, f in tilted.items() if any(abs(v - 1) > 1e-9 for v in f.values())}
        national = sum(counts[name] for name in tilted)
        for k in LANDSDEL:
            regional = sum(counts[name] * f[k] for name, f in tilted.items())
            rest = (total - regional) / (total - national)  # the untilted names fill what is left
            for name, n in counts.items():
                out[k][name] = n * tilted[name][k] if name in tilted else n * rest
        return out
