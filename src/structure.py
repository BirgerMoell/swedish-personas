"""Structured layer for v2: names, background, education, employment and occupation.

Everything here is sampled from Statistics Sweden tables in data/scb/ (see
src/fetch_scb_v2.py). Where no joint table exists, conditional tables are combined
under a naive-Bayes assumption; those places are marked ASSUMPTION.

  background   foreign-born / Swedish-born by parents' birthplace, by county, age, sex
  country      country of birth by county and sex, reweighted by the country's age profile
  heritage     name heritage group, from country of birth (ASSUMPTION: hand-written map)
  names        given name by sex, birth year and heritage; surname by heritage
  education    highest completed level by county, age and sex
  employment   employee rate by county, age band and sex, adjusted for education
  occupation   SSYK 3-digit by county, age, sex, adjusted for education and birth region,
               then SSYK 4-digit within it by education, age and sex; industry by occupation
"""

import bisect
import csv
import math
import re
from array import array
from collections import defaultdict
from itertools import accumulate
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCB = ROOT / "data" / "scb"
YEAR = 2025

BACKGROUND = {
    "08": "utrikes född",
    "4": "inrikes född med två utrikes födda föräldrar",
    "5": "inrikes född med en inrikes och en utrikes född förälder",
    "6": "inrikes född med två inrikes födda föräldrar",
}
EDUCATION = {
    "1": "förgymnasial utbildning kortare än 9 år",
    "2": "förgymnasial utbildning, 9 (10) år",
    "3": "gymnasial utbildning, högst 2 år",
    "4": "gymnasial utbildning, 3 år",
    "5": "eftergymnasial utbildning, mindre än 3 år",
    "6": "eftergymnasial utbildning, 3 år eller mer",
    "7": "forskarutbildning",
    "US": "uppgift om utbildningsnivå saknas",
}
POST_SECONDARY = {"5", "6", "7"}
# SSYK 22 (health professionals) and 23 (teachers) are dominated by licensed titles.
LICENSED_PREFIXES = ("22", "23")

# ---------------------------------------------------------------- heritage map
# ASSUMPTION: which name heritage a person born in a given country most likely carries.
# Weights are judgement, not statistics. SV shares cover adoptees and children of Swedes abroad.
_G = {
    "SV": "Norge Danmark Island",
    "BALK": "Jugoslavien|Bosnien och Hercegovina|Serbien|Kosovo|Kroatien|Nordmakedonien|Albanien|Serbien och Montenegro|Montenegro|Slovenien|Grekland|Cypern",
    "EEU": "Polen|Ukraina|Rumänien|Ryssland|Litauen|Ungern|Lettland|Bulgarien|Estland|Sovjetunionen|Belarus|Tjeckoslovakien|Tjeckien|Slovakien|Moldavien|Georgien|Armenien|Kazakstan",
    "EAS": "Thailand|Kina|Vietnam|Filippinerna|Mongoliet|Japan|Indonesien|Taiwan|Malaysia|Myanmar|Singapore|Kambodja|Hongkong|Laos|Nordkorea",
    "SAS": "Pakistan|Bangladesh|Nepal|Bhutan|Maldiverna",
    "AR": "Libanon|Egypten|Marocko|Sudan|Palestina|Saudiarabien|Tunisien|Jordanien|Förenade Arabemiraten|Libyen|Algeriet|Kuwait|Jemen|Qatar|Bahrain|Oman|Mauretanien",
    "IR": "Iran|Afghanistan",
    "HOA": "Somalia|Eritrea|Etiopien|Djibouti",
    "LAT": "Chile|Brasilien|Italien|Spanien|Peru|Portugal|Bolivia|Mexiko|Argentina|El Salvador|Kuba|Ecuador|Venezuela|Uruguay|Nicaragua|Dominikanska republiken|Guatemala|Costa Rica|Honduras|Panama|Paraguay|Malta",
    "AFR": "Nigeria|Demokratiska republiken Kongo|Uganda|Gambia|Kenya|Ghana|Burundi|Tanzania|Kamerun|Senegal|Elfenbenskusten|Rwanda|Zambia|Kongo|Liberia|Sierra Leone|Zimbabwe|Angola|Sydsudan|Guinea|Kap Verde|Moçambique|Togo|Centralafrikanska republiken|Mali|Tchad|Mauritius|Namibia|Guinea-Bissau|Madagaskar|Malawi|Benin|Burkina Faso|Botswana|Niger|Ekvatorialguinea|Seychellerna|Gabon|Lesotho",
}
HERITAGE = {c: {h: 1.0} for h, names in _G.items() for c in (names.split("|") if "|" in names else names.split())}
for _c in ("Tyskland", "Förenade kungariket (Storbritannien och Nordirland)", "Förenta staterna (USA)", "Nederländerna", "Frankrike",
           "Österrike", "Schweiz", "Australien", "Kanada", "Belgien", "Irland", "Nya Zeeland", "Luxemburg", "Monaco"):
    HERITAGE[_c] = {"WEU": 0.8, "SV": 0.2}
HERITAGE.update({
    "Sverige": {"SV": 1.0},
    "Finland": {"FI": 0.65, "SV": 0.35},
    "Syrien": {"AR": 0.85, "IR": 0.15},
    "Irak": {"AR": 0.65, "IR": 0.35},
    "Turkiet": {"TR": 0.55, "IR": 0.25, "AR": 0.20},
    "Indien": {"SAS": 0.85, "SV": 0.15},
    "Sri Lanka": {"SAS": 0.6, "SV": 0.4},
    "Sydkorea": {"SV": 0.7, "EAS": 0.3},
    "Colombia": {"LAT": 0.7, "SV": 0.3},
    "Sydafrika": {"WEU": 0.5, "AFR": 0.5},
    "Israel": {"WEU": 0.5, "AR": 0.5},
    "Azerbajdzjan": {"TR": 0.6, "IR": 0.4},
    "Uzbekistan": {"TR": 0.5, "IR": 0.3, "EEU": 0.2},
    "Kirgizistan": {"TR": 0.6, "EEU": 0.4},
    "Tadzjikistan": {"IR": 0.8, "EEU": 0.2},
    "Turkmenistan": {"TR": 0.8, "EEU": 0.2},
})
DEFAULT_HERITAGE = {"WEU": 1.0}
NORDIC = {"Finland", "Norge", "Danmark", "Island"}
NORTH_AMERICA = {"Förenta staterna (USA)", "Kanada", "Mexiko", "El Salvador", "Kuba", "Nicaragua", "Dominikanska republiken", "Guatemala", "Costa Rica", "Honduras", "Panama"}
SOUTH_AMERICA = {"Chile", "Brasilien", "Peru", "Bolivia", "Argentina", "Ecuador", "Venezuela", "Uruguay", "Paraguay", "Colombia"}
OCEANIA = {"Australien", "Nya Zeeland"}
EUROPE_HERITAGE = {"BALK", "EEU", "WEU", "LAT"}

SWEDISH_SURNAME = re.compile(
    r"(sson|son|sen|berg|bergh|ström|strand|gren|qvist|kvist|quist|lund|lundh|dahl|dal|holm|mark|stedt|blom|lind|lindh|gård|"
    r"ander|stam|bäck|fors|vall|wall|löf|sjö|hed|borg|feldt|felt|bring|ling|hag|näs|vik|wik|skog|sten|stål|hjelm|sköld|svärd|"
    r"crona|krona|stierna|blad|bladh|roth|rot|beck|man|mann|ell|én|ér|ius|in)$", re.I)


def read(name):
    with (SCB / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def birth_region(country):
    """Region of birth as used by the occupation register."""
    if country == "Sverige":
        return "SE"
    if country in NORDIC:
        return "NEXS"
    if country in NORTH_AMERICA:
        return "NAMA"
    if country in SOUTH_AMERICA:
        return "SAM"
    if country in OCEANIA:
        return "OCEA"
    heritage = max(HERITAGE.get(country, DEFAULT_HERITAGE).items(), key=lambda kv: kv[1])[0]
    if heritage in ("AFR", "HOA") or country in ("Egypten", "Marocko", "Sudan", "Tunisien", "Libyen", "Algeriet", "Mauretanien", "Sydafrika"):
        return "AFR"
    if heritage in EUROPE_HERITAGE or heritage == "SV":
        return "ÖEU"
    return "ASI"


def age_band5(age):
    return "100+5" if age >= 100 else "-4" if age < 5 else f"{age // 5 * 5}-{age // 5 * 5 + 4}"


def work_band(age):
    if age < 16 or age > 69:
        return None
    return "16-24" if age < 25 else "065-69" if age >= 65 else f"{age // 5 * 5}-{age // 5 * 5 + 4}"


class Table:
    """A weighted categorical distribution with O(log n) sampling."""

    __slots__ = ("items", "cum")

    def __init__(self, weights):
        pairs = [(k, w) for k, w in weights.items() if w > 0]
        self.items = [k for k, _ in pairs]
        self.cum = array("d", accumulate(w for _, w in pairs))

    def __bool__(self):
        return bool(self.items)

    def sample(self, rng):
        return self.items[bisect.bisect_right(self.cum, rng.random() * self.cum[-1])]


class Structure:
    def __init__(self):
        self._load_background()
        self._load_names()
        self._load_education()
        self._load_work()
        self._cache = {}

    # ------------------------------------------------------------ background
    def _load_background(self):
        bg = defaultdict(dict)
        for r in read("background_by_county_age_sex_2025"):
            age = 100 if r["Alder"].startswith("100") else int(r["Alder"])
            bg[(r["Region"], age, r["Kon"])][r["UtlBakgrund"]] = float(r["count"])
        self.background_tables = {k: Table(v) for k, v in bg.items()}
        by_county = defaultdict(lambda: defaultdict(float))
        for r in read("birth_country_by_county_2025"):
            name = r["Fodelseregion_text"].strip()
            if r["Fodelseregion"] == "TOTfod" or name in ("Sverige", "okänt födelseland", "övriga födelseländer"):
                continue
            by_county[(r["Region"], r["Kon"])][name] += float(r["count"])
        self.country_by_county = by_county
        profile = defaultdict(dict)
        total = defaultdict(float)
        for r in read("birth_country_by_age_2025"):
            name = r["Fodelseland_text"].strip()
            profile[(name, r["Kon"])][r["Alder"]] = float(r["count"])
            total[(name, r["Kon"])] += float(r["count"])
        self.age_profile = {k: {band: n / total[k] for band, n in v.items()} for k, v in profile.items()}

    def background(self, rng, county, age, sex):
        return self.background_tables[(county, age, sex)].sample(rng)

    def country(self, rng, county, age, sex, parents=False):
        """Country of birth of a foreign-born person, or of the parents of a Swedish-born one."""
        key = ("country", county, sex, None if parents else age_band5(age))
        table = self._cache.get(key)
        if table is None:
            weights = {}
            for name, n in self.country_by_county[(county, sex)].items():
                # ASSUMPTION: a country's age profile is the same in every county.
                share = 1.0 if parents else self.age_profile.get((name, sex), {}).get(age_band5(age), 0.0)
                weights[name] = n * share
            table = self._cache[key] = Table(weights) or Table(dict(self.country_by_county[(county, sex)]))
        return table.sample(rng)

    def heritage(self, rng, country):
        weights = HERITAGE.get(country, DEFAULT_HERITAGE)
        return rng.choices(list(weights), list(weights.values()))[0]

    # ----------------------------------------------------------------- names
    def _load_names(self):
        label = {(r["kind"], r["name"]): r["heritage"] for r in csv.DictReader((ROOT / "data/heritage/name_heritage.csv").open(encoding="utf-8"))}
        self.given = defaultdict(dict)        # (sex, heritage) -> {name: bearers 2020}
        self.given_heritage = {}
        for r in read("given_names_2020"):
            name, code = r["Tilltalsnamn_text"].strip(), r["Tilltalsnamn"].strip()
            heritage = label.get(("G", name))
            if heritage and code[-1] in "KM":
                sex = "1" if code[-1] == "M" else "2"
                self.given[(sex, heritage)][name] = float(r["count"])
                self.given_heritage[name] = heritage
        self.mean_age = {}
        for r in read("given_names_mean_age_2020"):
            code = r["Tilltalsnamn"].strip()
            if code[-1] in "KM":
                self.mean_age[("1" if code[-1] == "M" else "2", r["Tilltalsnamn_text"].strip())] = float(r["count"])
        self.top100 = defaultdict(dict)       # (sex, birth year) -> {name: people born that year}
        for r in read("given_names_top100_by_birth_year"):
            self.top100[(r["Tilltalsnamn"][0], int(r["Tid"]))][r["Tilltalsnamn_text"].strip()] = float(r["count"])
        self.top100_names = {(sex, name) for (sex, _), names in self.top100.items() for name in names}
        self.newborn = defaultdict(dict)      # (sex, year) -> {name: newborns}
        for r in read("newborn_names_1998_2022"):
            self.newborn[(r["Kon"], int(r["Tid"]))][r["Tilltalsnamn_text"].strip()] = float(r["count"])
        surnames = defaultdict(dict)
        for r in read("surnames_2020"):
            name = r["Efternamn_text"].strip()
            heritage = label.get(("S", name)) or ("SV" if SWEDISH_SURNAME.search(name) and " " not in name else None)
            if heritage:
                surnames[heritage][name] = float(r["count"])
        self.surnames = {h: Table(v) for h, v in surnames.items()}

    def _given_table(self, sex, heritage, birth_year, swedish_born):
        key = ("given", sex, heritage, birth_year, swedish_born)
        table = self._cache.get(key)
        if table is not None:
            return table
        own = self.given.get((sex, heritage), {})
        shared = self.given.get((sex, "INT"), {}) if heritage != "INT" else {}

        def weigh(pool):
            if swedish_born and birth_year >= 1998:
                year = self.newborn.get((sex, min(birth_year, 2022)), {})
                weights = {name: year[name] for name in pool if name in year}
                if weights:
                    return weights
            age_2020 = 2020 - birth_year
            exact = self.top100.get((sex, max(1922, min(2021, birth_year))), {}) if heritage == "SV" else {}
            weights = {}
            for name, stock in pool.items():
                if heritage == "SV" and (sex, name) in self.top100_names:
                    weights[name] = exact.get(name, 0.0)
                else:
                    # ASSUMPTION: bearers of a name are spread normally (sd 13 years) around its mean age.
                    z = (age_2020 - self.mean_age.get((sex, name), 40.0)) / 13.0
                    weights[name] = stock * math.exp(-0.5 * z * z) / (13.0 * 2.5066)
            return weights

        weights = weigh(own)
        extra = weigh(shared)
        if heritage != "SV" and sum(extra.values()) > 0:
            # ASSUMPTION: outside the Swedish pool, international names make up a fifth of given names.
            factor = 0.25 * sum(weights.values()) / sum(extra.values())
            extra = {name: w * factor for name, w in extra.items()}
        weights.update(extra)
        pool = {**own, **shared}
        table = self._cache[key] = Table(weights) or Table(pool)
        return table

    def names(self, rng, sex, age, background, heritage):
        """Return (given name, surname, name heritage)."""
        birth_year = YEAR - age
        swedish_born = background != "08"
        given_heritage = surname_heritage = heritage
        if background == "5":
            # One Swedish-born and one foreign-born parent. ASSUMPTION: Swedish-style given name,
            # and the foreign parent's surname half of the time.
            given_heritage = "SV"
            surname_heritage = heritage if rng.random() < 0.5 else "SV"
        elif heritage != "SV" and rng.random() < 0.07:
            surname_heritage = "SV"  # ASSUMPTION: surname taken through marriage
        if not self.given.get((sex, given_heritage)):
            given_heritage = "SV"
        given = self._given_table(sex, given_heritage, birth_year, swedish_born).sample(rng)
        surname = self.surnames.get(surname_heritage, self.surnames["SV"]).sample(rng)
        return given, surname, heritage if surname_heritage == heritage else "SV" if background != "5" else heritage

    # ------------------------------------------------------------- education
    def _load_education(self):
        edu = defaultdict(dict)
        national = defaultdict(lambda: defaultdict(float))
        for r in read("education_by_county_age_sex_2025"):
            age = int(r["Alder"].rstrip("+"))
            edu[(r["Region"], age, r["Kon"])][r["UtbildningsNiva"]] = float(r["count"])
            band = work_band(age)
            if band:
                national[(band, r["Kon"])][r["UtbildningsNiva"]] += float(r["count"])
        self.education_tables = {k: Table(v) for k, v in edu.items()}
        self.education_share = {k: {e: n / sum(v.values()) for e, n in v.items()} for k, v in national.items()}

    def education(self, rng, county, age, sex):
        return self.education_tables[(county, min(age, 95), sex)].sample(rng)

    # ------------------------------------------------------------------ work
    def _load_work(self):
        self.occ3 = defaultdict(dict)             # (county, band, sex) -> {occ3: n}
        self.occ3_label = {}
        employed = defaultdict(float)
        for r in read("occupation3_by_county_age_sex_2024"):
            key = (r["Region"], r["Alder"], r["Kon"])
            employed[key] += float(r["count"])
            if r["Yrke2012"] != "0002":
                self.occ3[key][r["Yrke2012"]] = float(r["count"])
                self.occ3_label[r["Yrke2012"]] = r["Yrke2012_text"].strip()
        population = defaultdict(float)
        with (ROOT / "data/scb_county_age_sex_marital_2025.csv").open(encoding="utf-8") as handle:
            for r in csv.DictReader(handle):
                age = 100 if r["age"].startswith("100") else int(r["age"])
                if work_band(age):
                    population[(r["county_code"], work_band(age), r["sex_code"])] += float(r["population"])
        self.employee_rate = {k: min(0.97, n / population[k]) for k, n in employed.items() if population.get(k)}

        self.occ4 = defaultdict(lambda: defaultdict(dict))   # (band, sex) -> occ4 -> {edu: n}
        self.occ4_label = {}
        occ3_edu = defaultdict(lambda: defaultdict(float))    # (band, sex, occ3) -> {edu: n}
        emp_edu = defaultdict(lambda: defaultdict(float))     # (band, sex) -> {edu: n}
        for r in read("occupation4_by_education_age_sex_2024"):
            code, n = r["Yrke2012"], float(r["count"])
            emp_edu[(r["Alder"], r["Kon"])][r["UtbNivaSun2020"]] += n
            if code == "0002":
                continue
            self.occ4[(r["Alder"], r["Kon"])][code][r["UtbNivaSun2020"]] = n
            self.occ4_label[code] = r["Yrke2012_text"].strip()
            occ3_edu[(r["Alder"], r["Kon"], code[:3])][r["UtbNivaSun2020"]] += n
        self.occ3_edu = occ3_edu
        self.employed_edu_share = {k: {e: n / sum(v.values()) for e, n in v.items()} for k, v in emp_edu.items()}

        occ3_region = defaultdict(lambda: defaultdict(float))  # (sex, occ3) -> {region: n}
        emp_region = defaultdict(lambda: defaultdict(float))
        for r in read("occupation4_by_birth_region_2024"):
            emp_region[r["Kon"]][r["Fodelseregion"]] += float(r["count"])
            occ3_region[(r["Kon"], r["Yrke2012"][:3])][r["Fodelseregion"]] += float(r["count"])
        self.occ3_region = occ3_region
        self.employed_region_share = {k: {g: n / sum(v.values()) for g, n in v.items()} for k, v in emp_region.items()}

        industry = defaultdict(lambda: defaultdict(float))
        for r in read("occupation4_by_industry_2024"):
            if r["SNI2007"] != "00":
                industry[r["Yrke2012"]][r["SNI2007_text"].strip()] += float(r["count"])
        self.industry = {k: Table(v) for k, v in industry.items()}

    def employee_probability(self, county, age, sex, edu):
        band = work_band(age)
        if band is None:
            return 0.0
        rate = self.employee_rate.get((county, band, sex), 0.0)
        if band == "16-24":  # ASSUMPTION: within the youngest band, employment rises steeply with age
            rate *= {16: 0.25, 17: 0.35, 18: 0.6, 19: 0.9}.get(age, 1.25) / 0.928
        # Bayes adjustment with national education shares among employees and in the population.
        among_employed = self.employed_edu_share.get((band, sex), {}).get(edu, 0.0)
        in_population = self.education_share.get((band, sex), {}).get(edu, 0.0)
        if in_population > 0:
            rate *= among_employed / in_population
        return min(0.97, rate)

    def occupation(self, rng, county, age, sex, edu, region):
        """Return (SSYK 4-digit code, occupation label, industry) for an employed person."""
        band = work_band(age)
        key = ("occ3", county, band, sex, edu, region)
        table = self._cache.get(key)
        if table is None:
            edu_share = self.employed_edu_share[(band, sex)].get(edu, 1e-9)
            region_share = self.employed_region_share[sex].get(region, 1e-9)
            weights = {}
            for occ3, n in self.occ3[(county, band, sex)].items():
                if occ3[:2] in LICENSED_PREFIXES and edu not in POST_SECONDARY:
                    continue
                by_edu = self.occ3_edu[(band, sex, occ3)]
                by_region = self.occ3_region[(sex, occ3)]
                # ASSUMPTION (naive Bayes): education and region of birth act independently given occupation.
                lift_edu = ((by_edu.get(edu, 0.0) + 0.5 * edu_share) / (sum(by_edu.values()) + 0.5)) / edu_share
                lift_region = ((by_region.get(region, 0.0) + 0.5 * region_share) / (sum(by_region.values()) + 0.5)) / region_share
                weights[occ3] = n * lift_edu * lift_region
            table = self._cache[key] = Table(weights) or Table(dict(self.occ3[(county, band, sex)]))
        occ3 = table.sample(rng)
        key = ("occ4", band, sex, edu, occ3)
        table = self._cache.get(key)
        if table is None:
            weights = {}
            for code, by_edu in self.occ4[(band, sex)].items():
                if code[:3] == occ3:
                    weights[code] = by_edu.get(edu, 0.0) + 0.01 * sum(by_edu.values())
            if not weights:  # no one of this sex and age in the group nationally: use all ages
                for (_, s), codes in self.occ4.items():
                    for code, by_edu in codes.items():
                        if s == sex and code[:3] == occ3:
                            weights[code] = weights.get(code, 0.0) + sum(by_edu.values())
            table = self._cache[key] = Table(weights)
        if not table:
            return occ3 + "0", self.occ3_label[occ3], ""
        occ4 = table.sample(rng)
        industry = self.industry[occ4].sample(rng) if occ4 in self.industry else ""
        return occ4, self.occ4_label[occ4], industry
