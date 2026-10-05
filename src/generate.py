"""Generate reproducible, wholly fictional Swedish personas from SCB aggregates."""

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

GIVEN_NAMES = {
    "1": ("Erik", "Lars", "Johan", "Anders", "Karl", "Oskar", "Nils", "David", "Ali", "Amir", "Mikael", "Daniel", "Axel", "Noah", "Elias", "Simon", "Linus", "Arvid", "Hugo", "William"),
    "2": ("Anna", "Maria", "Emma", "Sara", "Elin", "Linnéa", "Sofia", "Maja", "Fatima", "Amina", "Karin", "Eva", "Elsa", "Alma", "Ingrid", "Julia", "Nora", "Freja", "Olivia", "Ida"),
}
INTERESTS = ("odling", "fotografering", "matlagning", "löpning", "läsning", "musik", "friluftsliv", "spel", "föreningsliv", "film", "cykling", "språk", "hantverk", "historia", "dans", "fiske", "bakning", "simning", "natur", "konst", "teknik", "körsång", "vandring", "schack")
YOUNG_INTERESTS = ("bilderböcker", "lek", "sång", "byggklossar", "teckning", "sagor", "musik", "parker", "djur", "pussel")
SCHOOL_INTERESTS = ("läsning", "fotboll", "musik", "spel", "dans", "simning", "natur", "teckning", "cykling", "djur", "teknik", "film")
VALUES = ("en lugn vardag", "tid med vänner", "att lära sig nytt", "att kunna hjälpa andra", "balans mellan arbete och fritid", "att känna gemenskap", "att få vara kreativ", "att hålla kontakten med familjen")
GOALS = ("vill få bättre ordning på sin tid", "hoppas hitta mer tid för sina intressen", "försöker göra vardagen lite enklare", "vill lära sig något nytt i år", "vill engagera sig mer i närområdet", "planerar att resa mer inom Sverige")
COMMUNICATION = ("föredrar tydliga besked", "gillar att resonera tillsammans med andra", "uppskattar korta sammanfattningar", "vill gärna se konkreta exempel", "tar gärna tid på sig innan ett beslut")
EDUCATIONS = ("grundskola", "gymnasial utbildning", "eftergymnasial utbildning", "forskarutbildning")
SECTORS = {
    "vård och omsorg": ("undersköterska", "sjuksköterska", "vårdadministratör"),
    "utbildning": ("lärare", "förskollärare", "skoladministratör"),
    "handel": ("butiksmedarbetare", "inköpare", "lagerarbetare"),
    "industri": ("produktionstekniker", "montör", "maskinoperatör"),
    "bygg": ("snickare", "projektledare", "elektriker"),
    "transport": ("busschaufför", "logistiker", "lokförare"),
    "it och telekom": ("systemutvecklare", "it-supporttekniker", "testare"),
    "offentlig förvaltning": ("handläggare", "administratör", "utredare"),
    "hotell och restaurang": ("kock", "servitör", "receptionist"),
    "jordbruk och skogsbruk": ("lantbrukare", "skogsmaskinförare", "rådgivare"),
    "kultur och media": ("bibliotekarie", "producent", "formgivare"),
    "finans och företagstjänster": ("ekonomiassistent", "revisor", "kundrådgivare"),
}
MARITAL = {"OG": "ogift", "G": "gift", "ÄNKL": "änka eller änkling", "SK": "skild"}
COUNTRY_OF_BIRTH = ("Sverige", "Finland", "Norge", "Danmark", "Polen", "Tyskland", "Syrien", "Irak", "Iran", "Somalia", "Afghanistan", "Indien", "Ukraina")
COUNTRY_WEIGHTS = (80, 2, 1, 1, 2, 1, 3, 2, 2, 1, 1, 1, 3)


def read_csv(name):
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def employment(rng, age):
    if age < 6:
        return "barn", "", ""
    if age < 16:
        return "elev", "", ""
    if age < 20:
        status = rng.choices(("studerande", "anställd", "arbetssökande"), (76, 19, 5))[0]
    elif age < 25:
        status = rng.choices(("studerande", "anställd", "arbetssökande", "egenföretagare"), (38, 48, 10, 4))[0]
    elif age < 65:
        status = rng.choices(("anställd", "arbetssökande", "egenföretagare", "studerande", "utanför arbetskraften"), (72, 8, 9, 4, 7))[0]
    elif age < 70:
        status = rng.choices(("pensionär", "anställd", "egenföretagare"), (75, 20, 5))[0]
    else:
        status = "pensionär"
    if status not in ("anställd", "egenföretagare"):
        return status, "", ""
    if age < 21:
        sector, occupation = rng.choice((
            ("handel", "butiksmedarbetare"), ("handel", "lagerarbetare"),
            ("hotell och restaurang", "servitör"), ("industri", "montör"),
        ))
        return status, sector, occupation
    sector = rng.choice(tuple(SECTORS))
    return status, sector, rng.choice(SECTORS[sector])


def education(rng, age):
    if age < 6:
        return "ej påbörjad grundskola"
    if age < 16:
        return "pågående grundskola"
    if age < 20:
        return rng.choice(("grundskola", "pågående gymnasium"))
    if age < 24:
        return rng.choices(EDUCATIONS[:3], (15, 65, 20))[0]
    return rng.choices(EDUCATIONS, (14, 47, 37, 2))[0]


def description(row, rng):
    age = row["age"]
    age_text = "minst 100" if row["age_100_plus"] else str(age)
    first = row["first_name"]
    place = row["municipality"]
    intro = rng.choice((
        f"{first} är {age_text} år och bor i {place}.",
        f"I {place} bor {first}, {age_text} år.",
        f"{first}, {age_text} år, har sin vardag i {place}.",
        f"{first} bor i {place} och är {age_text} år.",
    ))
    status = row["employment_status"]
    if status == "barn":
        work = f"Vardagen rymmer mycket lek och tid tillsammans med närstående."
    elif status in ("anställd", "egenföretagare"):
        work = rng.choice((
            f"Till vardags arbetar {first} som {row['occupation']} inom {row['sector']}.",
            f"Arbetet som {row['occupation']} inom {row['sector']} är en del av vardagen.",
        ))
    elif status == "pensionär":
        work = f"{first} är pensionär och har tidigare haft ett arbetsliv med olika erfarenheter."
    elif status == "elev":
        work = f"{first} går i skolan."
    elif status == "studerande":
        work = f"Just nu studerar {first}."
    elif status == "arbetssökande":
        work = f"{first} söker för närvarande arbete."
    else:
        work = f"{first} står just nu utanför arbetskraften."
    if age < 6:
        interest = rng.choice((
            f"I vardagen tycker {first} om {row['interest_1']} och {row['interest_2']}.",
            f"{row['interest_1'].capitalize()} och {row['interest_2']} väcker ofta nyfikenhet.",
        ))
    else:
        interest = rng.choice((
            f"På fritiden tycker {first} om {row['interest_1']} och {row['interest_2']}.",
            f"{row['interest_1'].capitalize()} och {row['interest_2']} hör till intressena.",
            f"När det finns tid ägnar sig {first} gärna åt {row['interest_1']} eller {row['interest_2']}.",
        ))
    if age < 6:
        ending = f"{first} tycker om {row['value']} och {row['goal']}. {first} {row['communication']}."
    elif age < 16:
        ending = f"{first} uppskattar {row['value']} och {row['goal']}. {first} {row['communication']}."
    else:
        ending = f"{first} värdesätter {row['value']} och {row['goal']}. {first} {row['communication']}."
    return " ".join((intro, work, interest, ending))


def generate(size, seed, output):
    cells = [r for r in read_csv("scb_county_age_sex_marital_2025.csv") if int(r["population"]) > 0]
    municipalities = defaultdict(list)
    for r in read_csv("scb_municipality_2025.csv"):
        if int(r["population"]) > 0:
            municipalities[r["county_code"]].append(r)
    if not cells or len(municipalities) != 21:
        raise ValueError("Expected populated SCB cells for all 21 counties")
    rng = random.Random(seed)
    sampled_cells = rng.choices(cells, weights=[int(c["population"]) for c in cells], k=size)
    records = []
    for i, cell in enumerate(sampled_cells, 1):
        age = 100 if cell["age"].startswith("100+") else int(cell["age"])
        options = municipalities[cell["county_code"]]
        municipality = rng.choices(options, weights=[int(m["population"]) for m in options], k=1)[0]
        sex = cell["sex_code"]
        first = rng.choice(GIVEN_NAMES[sex])
        status, sector, occupation = employment(rng, age)
        interests = rng.sample(YOUNG_INTERESTS if age < 6 else SCHOOL_INTERESTS if age < 16 else INTERESTS, 2)
        if age < 6:
            value = rng.choice(("trygga rutiner", "lugna stunder", "lek med andra", "sång och berättelser"))
            goal = rng.choice(("utforskar nya lekar", "upptäcker sin omgivning", "lär sig nya ord", "provar nya aktiviteter"))
            communication = rng.choice(("visar tydligt vad som känns roligt", "söker gärna kontakt med andra", "är nyfiken på nya intryck"))
        elif age < 16:
            value = rng.choice(("tid med vänner", "nya saker att lära sig", "en rolig fritid", "tid med familjen"))
            goal = rng.choice(("vill prova en ny hobby", "ser fram emot nästa skolår", "vill bli bättre på något intresse", "upptäcker gärna nya platser"))
            communication = rng.choice(("gillar att ställa frågor", "berättar gärna om sina intressen", "vill gärna se konkreta exempel"))
        else:
            values = tuple(v for v in VALUES if age < 65 or v != "balans mellan arbete och fritid")
            value, goal, communication = rng.choice(values), rng.choice(GOALS), rng.choice(COMMUNICATION)
        row = {
            "id": f"SE-{i:06d}", "first_name": first, "age": age,
            "age_100_plus": cell["age"].startswith("100+"),
            "scb_sex": "man" if sex == "1" else "kvinna",
            "marital_status": MARITAL[cell["marital_code"]],
            "county_code": cell["county_code"], "county": cell["county"],
            "municipality_code": municipality["municipality_code"],
            "municipality": municipality["municipality"],
            "country_of_birth": rng.choices(COUNTRY_OF_BIRTH, weights=COUNTRY_WEIGHTS, k=1)[0],
            "education": education(rng, age), "employment_status": status,
            "sector": sector, "occupation": occupation,
            "interest_1": interests[0], "interest_2": interests[1],
            "value": value, "goal": goal,
            "communication": communication,
        }
        row["persona_sv"] = description(row, rng)
        records.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records), output, compression="zstd")
    report = {
        "rows": len(records), "seed": seed, "source_year": 2025,
        "county_counts": dict(Counter(row["county"] for row in records)),
        "sex_counts": dict(Counter(row["scb_sex"] for row in records)),
        "note": "SCB-weighted: joint county/age/sex/marital status; municipality county totals. Other attributes are illustrative heuristics, not calibrated to SCB."
    }
    (output.parent / "generation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(records):,} personas to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20251005)
    parser.add_argument("--output", type=Path, default=DATA / "swedish_personas_100k.parquet")
    args = parser.parse_args()
    generate(args.size, args.seed, args.output)
