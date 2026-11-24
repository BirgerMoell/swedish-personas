"""Build the seed records that the prose model writes from.

Usage: python3 src/prose_seeds.py [--n 1000] [--out data/pilot/seeds_1000.jsonl]

Each record joins one persona's structured columns, its name and Big Five scores
(the seeds table) and its health conditions. The sample is a plain random sample
of the 100k release, so the pilot has the same mix of ages and backgrounds.
"""

import argparse
import json
import random
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SEED = 20251005
STRUCTURED = (
    "sex", "age", "marital_status", "household_type", "education_level", "occupation", "occupation_code", "industry",
    "employment_status", "country_of_birth", "background", "kommun", "lan",
)
# T-scores (mean 50, sd 10) are turned into plain descriptions, as in Nemotron-Personas.
TRAITS = {
    "openness": (
        "håller sig helst till det välbekanta och beprövade", "är ganska praktiskt lagd och föredrar det konkreta",
        "är lagom nyfiken: öppen för nytt men utan att söka det", "är nyfiken och tycker om nya idéer och intryck",
        "är mycket nyfiken, fantasifull och söker ständigt nya intryck",
    ),
    "conscientiousness": (
        "tar dagen som den kommer och har svårt för planering", "är ganska spontan och inte särskilt noga med ordning",
        "är lagom ordningsam: planerar det viktiga och låter resten vara", "är organiserad och håller vad som lovats",
        "är mycket noggrann, målmedveten och planerar långt i förväg",
    ),
    "extraversion": (
        "är tydligt tillbakadragen och trivs bäst i eget sällskap", "är ganska lågmäld och föredrar små sällskap",
        "är varken utpräglat social eller tillbakadragen", "är utåtriktad och får energi av att träffa folk",
        "är mycket social, pratsam och söker sig till där det händer",
    ),
    "agreeableness": (
        "är rak, ifrågasättande och ger sig inte i första taget", "säger gärna emot och är ganska tävlingsinriktad",
        "är samarbetsvillig men står på sig när det behövs", "är varm, hjälpsam och mån om att andra har det bra",
        "är mycket omtänksam och sätter ofta andras behov före sina egna",
    ),
    "neuroticism": (
        "är mycket lugn och låter sig sällan stressas", "är trygg och tar motgångar med ro",
        "blir ibland stressad men hittar oftast balansen igen", "oroar sig lätt och tar åt sig av motgångar",
        "har nära till oro och starka känslor och behöver tid för återhämtning",
    ),
}

TEXT_FIELDS = (
    "cultural_background", "skills_and_expertise", "hobbies_and_interests", "career_goals_and_ambitions", "professional_persona",
    "sports_persona", "arts_persona", "travel_persona", "culinary_persona", "healthcare_persona", "persona",
)
# How a field's first sentence starts. One is drawn per field and persona, because the first pilot
# showed that the model otherwise opens the same field the same way for almost everyone.
OPENINGS = (
    "med personens namn som subjekt",
    "med personens namn som subjekt",
    "med en tidsbestämning (till exempel en veckodag, en årstid, ett årtal eller en tid på dygnet)",
    "med en verklig plats",
    "med en bisats (till exempel med Eftersom, När, Trots att, Sedan eller Om)",
    "med en sak, ett föremål eller en maträtt",
    "med en annan människa i personens liv",
    "med en konkret handling eller vana, utan att nämna namnet först",
)
# Leisure ideas with an age span. Twelve are shown per persona as inspiration, not as facts: the
# shares are not statistics, the draw only keeps the model from giving everyone the same hobbies.
LEISURE = (
    (0, 5, "sandlåda, pulka, pussel, klossar, sagostunder, vattenlek, lera, gunga, dansa till barnmusik, djurböcker, balanscykel, rita med kritor, öppna förskolan, bada på badhus, plocka pinnar och stenar"),
    (6, 12, "fotboll i knattelag, innebandy, simskola, ridskola, scouterna, kulturskolan, pärlplattor, samlarkort, kojbygge, minecraft, schackklubb, gymnastik, bandy, friidrott, serieteckning, fiske från brygga, bakning, lego, cykelcross, kör, blockflöjt, programmering på fritids, skidor, skridskor, pingis"),
    (13, 19, "e-sport, moped, fotboll, handboll, basket, gym, skateboard, replokal med band, epa-traktor, ridning, dans, teater, cosplay, fotografering, second hand-kläder, anime, ungdomsgård, konfirmationsläger, jakt med en förälder, innebandy, kampsport, sy om kläder, podcast, teckna manga, spela gitarr, klättring, längdskidor"),
    (16, 100, "kolonilott, släktforskning, körsång, bridge, boule, älgjakt, flugfiske, pimpelfiske, biodling, vävning, stickning, virkning, lapptäcken, träsvarvning, veteranbilar, mc-åkning, segling, kajak, långfärdsskridskor, orientering, löpning, cykelpendling, padel, golf, bowling, dart, linedance, bugg, folkdans, spelmanslag, blåsorkester, rockband, vinylskivor, amatörteater, revy, akvarell, keramik, silversmide, fågelskådning, svampplockning, bärplockning, surdegsbakning, ölbryggning, syltning och saftning, vinprovning, grilla och röka kött, brädspel, rollspel, schack, frågesport, tv-spel, fantasyfotboll, travet, speedway, ishockey på läktaren, supporterklubb, hembygdsförening, idrottsledare, valberedning i bostadsrättsförening, röda korset, kyrkans syförening, moskéns ungdomsverksamhet, kulturförening, läxhjälp som volontär, hundkurs, agility, hästar, höns, akvarium, husrenovering, möbelrenovering, loppisfynd, antikviteter, släpvagnssemester med husvagn, fjällvandring, tältning, vinterbad, bastu, yoga, styrketräning, simning, vattengympa, promenadgrupp, stavgång, korsord, sudoku, ljudböcker, deckare, poesi, lokalhistoria, dokumentärer, bio, opera, stand-up, museer, fotoklubb, drönarflygning, amatörradio, modelljärnväg, 3d-skrivare, programmering, elektronikbyggen, mekande med bilar, båtmotorer, snöskoter, fyrhjuling, skogsarbete på egen mark, vedhuggning, trädgårdsodling, växthus, krukväxter, biodlarförening, matlagning från hemlandet, bakning till kalas, teceremoni, dominospel, backgammon, kortspel, cricket, futsal, basket, bordtennis, brottning, boxning, zumba, dans för seniorer, pensionärsförening, bingo, resor med buss, sommarstuga, skärgårdsbåt"),
)


def leisure_ideas(rng, age, k=12):
    pool = [item.strip() for low, high, items in LEISURE if low <= age <= high for item in items.split(",")]
    return rng.sample(pool, min(k, len(pool)))


def describe(trait, score):
    bucket = 0 if score < 35 else 1 if score < 45 else 2 if score <= 55 else 3 if score <= 65 else 4
    return TRAITS[trait][bucket]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--data", default=str(ROOT / "data/swedish_personas_100k.parquet"))
    ap.add_argument("--out", default=str(ROOT / "data/pilot/seeds_1000.jsonl"))
    args = ap.parse_args()
    data = Path(args.data)
    rows = pq.read_table(data).to_pylist()
    seeds = {s["uuid"]: s for s in pq.read_table(data.with_name(data.stem + "_seeds.parquet")).to_pylist()}
    conditions = {}
    for c in pq.read_table(data.with_name(data.stem + "_conditions.parquet")).to_pylist():
        conditions.setdefault(c["uuid"], []).append(c["condition"])
    picked = random.Random(SEED).sample(range(len(rows)), args.n)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for i in sorted(picked):
            row, seed = rows[i], seeds[rows[i]["uuid"]]
            record = {"uuid": row["uuid"], "first_name": seed["first_name"], "last_name": seed["last_name"],
                      "birth_year": seed["birth_year"], "parents_country_of_birth": seed["parents_country_of_birth"]}
            record.update({k: row[k] for k in STRUCTURED})
            record["conditions"] = sorted(set(conditions.get(row["uuid"], [])))
            record["personality"] = [describe(t, seed[t]) for t in TRAITS]
            style = random.Random(f"{SEED}:{row['uuid']}")  # separate stream: does not disturb the sample
            record["openings"] = {field: style.choice(OPENINGS) for field in TEXT_FIELDS}
            record["leisure_ideas"] = leisure_ideas(style, row["age"])
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{args.n} seed records -> {out}")


if __name__ == "__main__":
    main()
