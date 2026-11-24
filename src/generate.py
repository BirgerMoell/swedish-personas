"""Generate reproducible, wholly fictional Swedish personas in the Nemotron-Personas schema.

Demographics (county x age x sex x marital status, municipality) come from SCB aggregates.
All other fields are rule-based (no LLM) and are laid out exactly like the columns of
nvidia/Nemotron-Personas-France, with Swedish locale fields (`kommun`, `lan`).
"""

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from statistics import NormalDist

import pyarrow as pa
import pyarrow.parquet as pq

from structure import BACKGROUND, EDUCATION, Structure, birth_region

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Column order follows Nemotron-Personas-France; municipality/county replace commune/departement.
SCHEMA = pa.schema([
    ("uuid", pa.string()),
    ("professional_persona", pa.string()),
    ("healthcare_persona", pa.string()),
    ("sports_persona", pa.string()),
    ("arts_persona", pa.string()),
    ("travel_persona", pa.string()),
    ("culinary_persona", pa.string()),
    ("persona", pa.string()),
    ("cultural_background", pa.string()),
    ("skills_and_expertise", pa.string()),
    ("skills_and_expertise_list", pa.string()),
    ("hobbies_and_interests", pa.string()),
    ("hobbies_and_interests_list", pa.string()),
    ("career_goals_and_ambitions", pa.string()),
    ("sex", pa.string()),
    ("age", pa.int64()),
    ("marital_status", pa.string()),
    ("household_type", pa.string()),
    ("education_level", pa.string()),
    ("occupation", pa.string()),
    ("occupation_code", pa.string()),
    ("industry", pa.string()),
    ("employment_status", pa.string()),
    ("country_of_birth", pa.string()),
    ("background", pa.string()),
    ("kommun", pa.string()),
    ("lan", pa.string()),
    ("country", pa.string()),
])

# Optional companion table: one row per sampled condition, keyed by persona uuid.
CONDITION_SCHEMA = pa.schema([("uuid", pa.string()), ("source", pa.string()), ("code", pa.string()), ("condition", pa.string())])

# Companion table with the latent attributes behind each persona (not part of the Nemotron schema).
# The Big Five T-scores (mean 50, sd 10, clipped to 20-80) follow the Nemotron-Personas design.
SEED_SCHEMA = pa.schema([
    ("uuid", pa.string()), ("first_name", pa.string()), ("last_name", pa.string()), ("name_heritage", pa.string()),
    ("parents_country_of_birth", pa.string()), ("birth_year", pa.int64()),
    ("openness", pa.int64()), ("conscientiousness", pa.int64()), ("extraversion", pa.int64()),
    ("agreeableness", pa.int64()), ("neuroticism", pa.int64()),
])
# Typical age at the end of each education level, used for years of work experience.
WORK_START = {"1": 16, "2": 16, "3": 18, "4": 19, "5": 21, "6": 23, "7": 28, "US": 19}

# v1 name lists, kept for reference only; v2 samples names in structure.py.
GIVEN_NAMES = {
    "1": ("Erik", "Lars", "Johan", "Anders", "Karl", "Oskar", "Nils", "David", "Ali", "Amir", "Mikael", "Daniel", "Axel", "Noah", "Elias", "Simon", "Linus", "Arvid", "Hugo", "William"),
    "2": ("Anna", "Maria", "Emma", "Sara", "Elin", "Linnéa", "Sofia", "Maja", "Fatima", "Amina", "Karin", "Eva", "Elsa", "Alma", "Ingrid", "Julia", "Nora", "Freja", "Olivia", "Ida"),
}
SURNAMES = ("Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson", "Larsson", "Olsson", "Persson", "Svensson", "Gustafsson", "Pettersson", "Jonsson", "Jansson", "Hansson", "Bengtsson", "Jönsson", "Lindberg", "Lindström", "Lindqvist", "Lundgren", "Berg", "Axelsson", "Bergström", "Lundberg", "Månsson", "Nyström", "Holm", "Sandberg", "Forsberg", "Ekström", "Hedlund", "Dahlberg", "Samuelsson", "Wikström", "Sjöberg", "Hassan", "Ahmed", "Kowalski", "Virtanen", "Haddad")
PRONOUN = {"1": "han", "2": "hon"}
POSSESSIVE = {"1": "hans", "2": "hennes"}

MARITAL = {"OG": "ogift", "G": "gift", "ÄNKL": "änka eller änkling", "SK": "skild"}
COUNTRY_OF_BIRTH = ("Sverige", "Finland", "Norge", "Danmark", "Polen", "Tyskland", "Syrien", "Irak", "Iran", "Somalia", "Afghanistan", "Indien", "Ukraina")
COUNTRY_WEIGHTS = (80, 2, 1, 1, 2, 1, 3, 2, 2, 1, 1, 1, 3)

# sector -> occupation -> typical skills
OCCUPATIONS = {
    "vård och omsorg": {
        "undersköterska": ("omvårdnad", "dokumentation", "bemötande", "ergonomi"),
        "sjuksköterska": ("medicinsk bedömning", "läkemedelshantering", "patientsäkerhet", "teamsamverkan"),
        "vårdadministratör": ("patientadministration", "journalsystem", "tidsbokning", "sekretess"),
    },
    "utbildning": {
        "lärare": ("lektionsplanering", "pedagogik", "bedömning", "klassrumsledning"),
        "förskollärare": ("pedagogisk dokumentation", "lekbaserat lärande", "föräldrakontakt", "språkutveckling"),
        "skoladministratör": ("schemaläggning", "elevadministration", "ekonomi", "kommunikation"),
    },
    "handel": {
        "butiksmedarbetare": ("kundbemötande", "kassahantering", "varupresentation", "lagerkontroll"),
        "inköpare": ("leverantörsförhandling", "prisanalys", "avtal", "beställningssystem"),
        "lagerarbetare": ("plock och pack", "truckkörning", "lagersaldo", "säkerhetsrutiner"),
    },
    "industri": {
        "produktionstekniker": ("processförbättring", "felsökning", "kvalitetssäkring", "lean"),
        "montör": ("manuell montering", "ritningsläsning", "precision", "kvalitetskontroll"),
        "maskinoperatör": ("CNC-maskiner", "underhåll", "processövervakning", "säkerhet"),
    },
    "bygg": {
        "snickare": ("ritningsläsning", "formsättning", "finsnickeri", "måttagning"),
        "projektledare": ("tidsplanering", "budget", "upphandling", "arbetsmiljö"),
        "elektriker": ("installation", "felsökning", "elsäkerhet", "styrsystem"),
    },
    "transport": {
        "busschaufför": ("trafiksäkerhet", "kundservice", "rutt- och tidtabellskunskap", "stresshantering"),
        "logistiker": ("transportplanering", "lagerstyrning", "affärssystem", "tullhantering"),
        "lokförare": ("signalsystem", "säkerhetsföreskrifter", "punktlighet", "felanmälan"),
    },
    "it och telekom": {
        "systemutvecklare": ("programmering", "systemdesign", "versionshantering", "kodgranskning"),
        "it-supporttekniker": ("felsökning", "användarstöd", "nätverk", "dokumentation"),
        "testare": ("testautomation", "kravanalys", "felrapportering", "kvalitetssäkring"),
    },
    "offentlig förvaltning": {
        "handläggare": ("ärendehantering", "juridisk tolkning", "utredning", "bemötande"),
        "administratör": ("diarieföring", "ekonomiadministration", "mötesplanering", "verksamhetssystem"),
        "utredare": ("dataanalys", "källkritik", "rapportskrivning", "intervjuteknik"),
    },
    "hotell och restaurang": {
        "kock": ("matlagning", "menyplanering", "livsmedelshygien", "kostnadskontroll"),
        "servitör": ("gästbemötande", "dryckeskunskap", "försäljning", "tempo under press"),
        "receptionist": ("bokningssystem", "gästservice", "språkkunskaper", "problemlösning"),
    },
    "jordbruk och skogsbruk": {
        "lantbrukare": ("växtodling", "djurhållning", "maskinunderhåll", "lantbruksekonomi"),
        "skogsmaskinförare": ("skördarkörning", "skogsvård", "planering av gallring", "maskinunderhåll"),
        "rådgivare": ("växtnäringsplanering", "stödregler", "lönsamhetskalkyler", "rådgivning"),
    },
    "kultur och media": {
        "bibliotekarie": ("informationssökning", "litteraturkännedom", "läsfrämjande", "katalogisering"),
        "producent": ("projektstyrning", "budget", "manusutveckling", "samordning"),
        "formgivare": ("typografi", "bildbehandling", "varumärkesprofil", "layout"),
    },
    "finans och företagstjänster": {
        "ekonomiassistent": ("bokföring", "fakturahantering", "avstämningar", "affärssystem"),
        "revisor": ("revision", "regelverk", "riskbedömning", "analys"),
        "kundrådgivare": ("sparrådgivning", "kundrelationer", "produktkunskap", "regelefterlevnad"),
    },
}
ALL_OCCUPATIONS = [(s, o) for s, d in OCCUPATIONS.items() for o in d]
TEEN_JOBS = (("handel", "butiksmedarbetare"), ("handel", "lagerarbetare"), ("hotell och restaurang", "servitör"), ("industri", "montör"))

# county code -> (outdoor activity, local dish, cultural landmark)
REGION = {
    "01": ("skärgårdsutflykter med Waxholmsbåt", "toast skagen", "Moderna museet och Kulturhuset"),
    "03": ("promenader längs Fyrisån", "våfflor vid valborgsfirandet", "Uppsala domkyrka och Gamla Uppsala"),
    "04": ("cykelturer kring Mälaren", "stekt gös från Mälaren", "Gripsholms slott"),
    "05": ("turer längs Göta kanal", "kalops", "Vadstena slott och Norrköpings industrilandskap"),
    "06": ("bad och promenader vid Vättern", "polkagrisar från Gränna", "Husqvarna fabriksmuseum"),
    "07": ("kanotpaddling i sjölandskapet", "kroppkakor", "Glasriket"),
    "08": ("sommardagar på Öland", "kroppkakor med fläsk", "Kalmar slott och Ölands alvar"),
    "09": ("promenader bland raukarna", "saffranspannkaka", "Medeltidsveckan i Visby"),
    "10": ("kajakpaddling i skärgården", "böckling", "Karlskrona örlogsstad"),
    "12": ("strandpromenader på Österlen", "äggakaka", "Malmö Live och Österlens konstrunda"),
    "13": ("dagar vid Hallandskusten", "laxsoppa", "Varbergs fästning"),
    "14": ("segling i Göteborgs skärgård", "räkmacka", "Slottsskogen och Göteborgs konserthus"),
    "17": ("fiske i Klarälven", "värmlandskorv", "Mårbacka och Selma Lagerlöfs värld"),
    "18": ("vandring i Kilsbergen", "ärtsoppa med pannkakor", "Örebro slott och Wadköping"),
    "19": ("skridskoåkning på Mälaren", "plättar med sylt", "Anundshög och Västerås konstmuseum"),
    "20": ("skidåkning runt Siljan", "kolbullar", "Falu koppargruva och Vasaloppet"),
    "21": ("vandring längs Hälsingeleden", "ostkaka med sylt", "Hälsingegårdarna"),
    "22": ("vandring på Höga kusten", "surströmming", "Sundsvalls stenstad"),
    "23": ("fjällvandring och skidåkning i Åre", "renskav", "Jamtli och Storsjön"),
    "24": ("skidturer i Umeåtrakten", "västerbottensostpaj", "Bildmuseet i Umeå"),
    "25": ("norrskenskvällar i Abisko", "älgkött", "Jukkasjärvi och Kiruna"),
}

HOBBIES_CHILD = ("lek med byggklossar", "bilderböcker", "sång och rim", "teckning", "sagostunder", "pussel", "lek på lekplatsen", "djur", "dans till barnmusik")
HOBBIES_YOUTH = ("fotboll", "gaming", "teckning", "musik", "dans", "simning", "cykling", "bakning", "läsning", "film", "programmering", "scouting", "innebandy", "ridning")
HOBBIES_ADULT = ("odling", "fotografering", "matlagning", "löpning", "läsning", "musik", "friluftsliv", "tv-spel", "föreningsliv", "film", "cykling", "språkstudier", "hantverk", "släktforskning", "dans", "fiske", "bakning", "simning", "naturstudier", "målning", "körsång", "vandring", "schack", "renovering", "bilmek", "svampplockning")
SPORTS_CHILD = ("leker och springer på skolgården", "går på simskola", "spelar fotboll med kompisarna", "åker pulka på vintern", "provar gymnastik", "cyklar på cykelvägen")
SPORTS_ADULT = ("tränar på gym två gånger i veckan", "springer i motionsspåret", "spelar innebandy i en korpserie", "åker längdskidor när det finns snö", "simmar en kvart varje vecka", "går långpromenader med hunden", "spelar padel med vänner", "cyklar till jobbet året runt", "går på yoga", "spelar fotboll i veteranlag")
SPORTS_SENIOR = ("går dagliga promenader", "deltar i vattengympa", "spelar boule", "går stavgång med grannarna", "gör sittgympa", "cyklar korta turer på sommaren")
SPORTS_FOLLOW = ("följer hockey i tv", "kollar på allsvensk fotboll", "följer Vasaloppet varje år", "tittar på friidrott", "följer landslagets matcher")
ARTS_CHILD = ("ritar och målar", "sjunger i förskolan", "lyssnar på sagor", "bygger i lera", "dansar när musiken går på")
ARTS_ADULT = ("läser deckare", "går på bio", "lyssnar på ljudböcker", "tittar på dokumentärer", "går på konserter", "besöker lokala konstutställningar", "sjunger i kör", "stickar och syr", "målar akvarell", "fotograferar landskap", "spelar gitarr")
TRAVEL_CHILD = ("åker gärna på utflykter till lekparker", "tycker om resor till mormor och morfar", "gillar tågresor")
TRAVEL_ADULT = ("campar med husvagn på somrarna", "reser gärna med tåg inom Sverige", "åker på charter till Medelhavet", "besöker släkt i utlandet varje sommar", "gillar stadsweekender i Europa", "hyr stuga i fjällen", "drömmer om en resa genom Japan")
TRAVEL_SENIOR = ("åker på bussresor med pensionärsföreningen", "besöker barnbarnen över helgerna", "gör kryssningar på Östersjön", "reser lugnt till Kanarieöarna på vintern")
CULINARY_STAPLES = ("pytt i panna", "köttbullar med potatis", "fiskgratäng", "ugnsbakad lax", "köttfärssås", "linssoppa", "grönsakssoppa", "pannkakor", "stekt strömming", "gryta med rotfrukter", "wraps", "pasta med grönsaker")
CULINARY_STYLE = ("lagar vardagsmat enkelt och snabbt", "älskar att baka på helgerna", "provar nya recept varje månad", "lagar helst mat från grunden", "bjuder gärna vänner på middag", "föredrar husmanskost", "handlar lokalt när det går", "är nyfiken på mat från andra kök")
QUIRKS = (
    "planerar gärna i förväg och har ordning i kalendern",
    "är lugn och tar sig tid att lyssna",
    "har lätt för att prata med nya människor",
    "är nyfiken och provar gärna nya saker",
    "tycker om rutiner och förutsägbarhet",
    "är noggrann och går igenom detaljer två gånger",
    "oroar sig ibland i onödan men kommer snabbt vidare",
    "är hjälpsam och ställer upp för grannar",
    "föredrar små sällskap framför stora fester",
    "skjuter ibland upp saker tills det börjar bli bråttom",
    "har en torr humor som överraskar nya bekanta",
    "gillar att resonera och ifrågasätter vänligt",
)
CULTURE_VALUES = ("allemansrätten och närheten till naturen", "fikakulturen och att ta paus tillsammans", "lagom som ledstjärna", "föreningslivet och ideellt engagemang", "midsommar, lucia och andra högtider", "jämlikhet och tillit till grannar")
CAREER_GOALS = (
    "vill fördjupa sig inom sitt yrke och ta mer ansvar",
    "siktar på en roll med mer ledarskap",
    "vill hålla kompetensen aktuell genom vidareutbildning",
    "överväger att byta bransch inom några år",
    "vill få bättre balans mellan arbete och fritid",
    "funderar på att starta eget på sikt",
    "vill bli en trygg kollega som andra vänder sig till",
)
CAREER_GOALS_YOUNG = (
    "vill hitta ett yrke som känns meningsfullt",
    "hoppas få ett första fast jobb efter studierna",
    "vill prova olika arbeten innan hon eller han väljer inriktning",
)
CAREER_GOALS_OLD = (
    "trappar ner och vill använda tiden till engagemang i föreningar",
    "vill föra vidare sin yrkeserfarenhet till yngre",
    "planerar för pensionen och en trygg ekonomi",
)


# ---------------------------------------------------------------- health model
# Sampled from open Swedish statistics (see src/fetch_health.py). Each condition keeps its
# age- and sex-specific rate exactly. Conditions in the same cluster share a latent factor
# (a one-factor Gaussian copula), so they co-occur more often than independent draws would.
# ASSUMPTION: the loadings are judgement, chosen to give co-occurrence of a realistic order;
# they are not fitted to a joint source table (none is openly available).
COMORBIDITY = {
    "cardiometabolic": {"Diabetes": 0.6, "Högt blodtryck": 0.6, "Obesitas (BMI 30,0 eller högre)": 0.55,
                        "I25": 0.55, "I21": 0.55, "I50": 0.55, "I48": 0.45, "I63": 0.45, "I73": 0.5, "N18": 0.5, "E10": 0.3},
    "mental": {"Svår ängslan, oro eller ångest": 0.8, "Diagnosen depression av läkare": 0.8, "Svåra sömnbesvär": 0.6,
               "F31": 0.5, "F90": 0.4, "F84": 0.3, "F20": 0.3},
    "pain": {"Svår värk i rygg mm": 0.7, "Svår värk i rörelseorganen": 0.7, "Huvudvärk": 0.4,
             "M17": 0.45, "M16": 0.45, "M05": 0.4, "M06": 0.4, "G43": 0.35},
    "atopic": {"Allergi": 0.6, "Astma": 0.6, "Eksem": 0.55, "L20": 0.5, "J45": 0.5},
}
FACTOR_OF = {code: (factor, loading) for factor, codes in COMORBIDITY.items() for code, loading in codes.items()}
_NORMAL = NormalDist()
_THRESHOLD = {}


def has_condition(rng, factors, code, p):
    """Draw one condition with marginal probability p, correlated through its cluster factor."""
    if p <= 0:
        return False
    link = FACTOR_OF.get(code)
    if link is None or p >= 1:
        return rng.random() < p
    threshold = _THRESHOLD.get(p)
    if threshold is None:
        threshold = _THRESHOLD[p] = _NORMAL.inv_cdf(p)
    factor, loading = link
    if factor not in factors:
        factors[factor] = rng.gauss(0, 1)
    return loading * factors[factor] + (1 - loading * loading) ** 0.5 * rng.gauss(0, 1) < threshold
SOS_NAMES = {
    "I25": "kranskärlssjukdom", "I21": "hjärtinfarkt", "I48": "förmaksflimmer", "I50": "hjärtsvikt", "I63": "stroke",
    "I73": "kärlkramp i benen", "J44": "KOL", "J45": "astma", "F03": "demenssjukdom", "G20": "Parkinsons sjukdom",
    "G35": "MS", "G40": "epilepsi", "G43": "migrän", "C50": "bröstcancer", "C61": "prostatacancer", "C18": "tjocktarmscancer",
    "C34": "lungcancer", "C43": "hudcancer (malignt melanom)", "M17": "knäartros", "M16": "höftartros", "M81": "benskörhet",
    "M05": "reumatoid artrit", "M06": "ledgångsreumatism", "H25": "grå starr", "N40": "prostataförstoring", "N18": "kronisk njursjukdom",
    "F20": "schizofreni", "F31": "bipolär sjukdom", "F84": "autismspektrumtillstånd", "F90": "ADHD", "E10": "typ 1-diabetes",
    "K21": "sura uppstötningar (reflux)", "K50": "Crohns sjukdom", "K51": "ulcerös kolit", "K80": "gallsten", "L20": "atopiskt eksem",
    "L40": "psoriasis", "H66": "öroninflammation", "J35": "besvär med halsmandlar", "N20": "njursten",
}
# Covered by the self-reported survey for people aged 16+, so not drawn again from the register table.
SOS_ADULT_EXCLUDED = {"J45", "E10", "F32", "F41", "F00", "G30"}
FOHM_NAMES = {
    "Allergi": "allergi", "Astma": "astma", "Diabetes": "diabetes", "Eksem": "eksem", "Huvudvärk": "återkommande huvudvärk",
    "Högt blodtryck": "högt blodtryck", "Inkontinens": "inkontinensbesvär", "Magtarmbesvär": "magtarmbesvär", "Tinnitus": "tinnitus",
    "Yrsel": "yrsel", "Svår värk i rygg mm": "svår värk i ryggen", "Svår värk i rörelseorganen": "svår värk i rörelseorganen",
    "Obesitas (BMI 30,0 eller högre)": "fetma", "Svår ängslan, oro eller ångest": "svår oro och ångest",
    "Diagnosen depression av läkare": "depression", "Svåra sömnbesvär": "svåra sömnbesvär",
}
FOHM_BANDS = (("16-29", 16, 29), ("30-44", 30, 44), ("45-64", 45, 64), ("65-84", 65, 84), ("85-", 85, 200))
PATIENT_STYLE_CHILD = ("går på kontroller via barn- och elevhälsan", "har vårdnadshavare som sköter kontakterna med vården")
PATIENT_STYLE = (
    "går på regelbundna kontroller på vårdcentralen",
    "söker vård först när besvären stör vardagen",
    "har koll på sina läkemedel och fyller i förväg på apoteket",
    "ringer 1177 för råd innan {pron} kontaktar vården",
    "följer läkarens råd men skjuter ibland upp provtagningar",
    "för egna anteckningar om symtom inför vårdbesök",
    "försöker förebygga besvären med motion och kost",
)
PATIENT_STYLE_SENIOR = (
    "har läkemedel i dosett och återkommande besök på vårdcentralen",
    "får hjälp av anhöriga med vårdkontakter",
    "går på regelbundna kontroller och uppskattar fast vårdkontakt",
    "är trygg med hemtjänst och hembesök när det behövs",
)
HEALTHY_ADULT = ("har inga kända långvariga sjukdomar och söker vård mest för vaccinationer och akuta besvär", "är i huvudsak frisk och går sällan till vårdcentralen", "har god hälsa och tar hand om sig med motion och sömn")
HEALTHY_CHILD = ("är i huvudsak frisk och följer barnhälsovårdens och skolhälsovårdens kontroller", "är frisk och går främst på vaccinationer och rutinkontroller")


def load_health():
    sos = defaultdict(dict)  # (code) -> {(band_start_age, sex): p}
    for r in read_csv("health_socialstyrelsen.csv"):
        low = int(r["age_band"].rstrip("+").split("-")[0])
        sos[r["icd10"]][(low, r["sex"])] = float(r["patients_per_100k"]) / 100_000
    fohm = defaultdict(dict)
    for r in read_csv("health_folkhalsomyndigheten.csv"):
        fohm[r["condition"]][(r["age_band"], r["sex"])] = float(r["percent"]) / 100
    return dict(sos), dict(fohm)


def sample_conditions(rng, health, age, sex):
    """Return [(source, code, swedish_name)] for one person."""
    sos, fohm = health
    out = []
    factors = {}
    band_low = min(85, (age // 5) * 5)
    for code, table in sos.items():
        if code not in SOS_NAMES or (age >= 16 and code in SOS_ADULT_EXCLUDED):
            continue
        if has_condition(rng, factors, code, table.get((band_low, sex), 0.0)):
            out.append(("socialstyrelsen", code, SOS_NAMES[code]))
    if age >= 16:
        band = next(name for name, lo, hi in FOHM_BANDS if lo <= age <= hi)
        for condition, table in fohm.items():
            if has_condition(rng, factors, condition, table.get((band, sex), 0.0)):
                out.append(("folkhalsomyndigheten", condition, FOHM_NAMES[condition]))
    return out


def healthcare_text(rng, name, first, pron, age, conditions):
    if not conditions:
        return f"{name} {rng.choice(HEALTHY_CHILD if age < 16 else HEALTHY_ADULT)}."
    self_reported = [c[2] for c in conditions if c[0] == "folkhalsomyndigheten"]
    registered = [c[2] for c in conditions if c[0] == "socialstyrelsen"]
    parts = []
    if self_reported:
        parts.append(f"lever med {join_list(self_reported[:3])}")
    if registered:
        parts.append(f"har kontakt med specialistvården för {join_list(registered[:3])}" if self_reported else f"är aktuell inom specialistvården för {join_list(registered[:3])}")
    pool = PATIENT_STYLE_CHILD if age < 16 else PATIENT_STYLE_SENIOR if age >= 75 else PATIENT_STYLE
    style = rng.choice(pool).format(pron=pron)
    return f"{name} {', '.join(parts)} och {style}."


def read_csv(name):
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def employment(rng, structure, county_code, age, sex_code, edu, region):
    """Return (status, occupation code, occupation label, industry)."""
    if age < 6:
        return "barn", "", "", ""
    if age < 16:
        return "elev", "", "", ""
    if rng.random() < structure.employee_probability(county_code, age, sex_code, edu):
        status = "anställd"
    elif age < 20:
        status = rng.choices(("studerande", "arbetssökande"), (94, 6))[0]
    elif age < 25:
        status = rng.choices(("studerande", "arbetssökande", "utanför arbetskraften"), (75, 20, 5))[0]
    elif age < 65:
        # ASSUMPTION: split of people who are not employees; the register covers employees only.
        status = rng.choices(("egenföretagare", "arbetssökande", "studerande", "utanför arbetskraften"), (28, 22, 12, 38))[0]
    elif age < 70:
        status = rng.choices(("pensionär", "egenföretagare"), (93, 7))[0]
    else:
        status = "pensionär"
    if status not in ("anställd", "egenföretagare"):
        return status, "", "", ""
    code, label, industry = structure.occupation(rng, county_code, age, sex_code, edu, region)
    return status, code, label, industry


def education(rng, structure, county_code, age, sex_code):
    """Return (SCB level code or '', label)."""
    if age < 6:
        return "", "förskola"
    if age < 16:
        return "", "pågående grundskola"
    code = structure.education(rng, county_code, age, sex_code)
    return code, EDUCATION[code]


def lower_first(text):
    """Lower-case the first letter unless the word is an acronym (IT-arkitekter)."""
    return text if text[1:2].isupper() else text[:1].lower() + text[1:]


def tidy_name(name):
    """SCB writes double names as 'Lars-erik' or 'Anna Karin'; restore the capitals."""
    return "-".join(" ".join(w[:1].upper() + w[1:] for w in part.split(" ")) for part in name.split("-"))


def household(rng, age, marital):
    if age < 18:
        return rng.choices(("bor med båda föräldrarna", "bor med en förälder", "bor växelvis hos båda föräldrarna"), (66, 26, 8))[0]
    if marital == "ÄNKL":
        return "bor på äldreboende" if age >= 85 and rng.random() < 0.25 else "ensamhushåll"
    if marital == "G":
        kids = 0.55 if age < 50 else 0.15 if age < 60 else 0.03
        return "par med hemmavarande barn" if rng.random() < kids else "par utan hemmavarande barn"
    if age < 25:
        return rng.choices(("bor hos föräldrar", "ensamhushåll", "sambo utan barn"), (45, 40, 15))[0]
    if marital == "SK":
        return rng.choices(("ensamhushåll", "ensamstående med hemmavarande barn", "sambo utan barn"), (60, 15 if age < 55 else 3, 25))[0]
    if age >= 65:
        return rng.choices(("ensamhushåll", "sambo utan barn"), (70, 30))[0]
    return rng.choices(("ensamhushåll", "sambo utan barn", "sambo med hemmavarande barn", "ensamstående med hemmavarande barn"), (50, 22, 18, 10))[0]


def join_list(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " och " + items[-1]


def build_row(rng, health, structure, cell, municipality):
    age = 100 if cell["age"].startswith("100+") else int(cell["age"])
    sex_code = cell["sex_code"]
    county_code = cell["county_code"]
    background = structure.background(rng, county_code, age, sex_code)
    birth = structure.country(rng, county_code, age, sex_code) if background == "08" else "Sverige"
    parents = birth if background == "08" else structure.country(rng, county_code, age, sex_code, parents=True) if background in ("4", "5") else "Sverige"
    heritage = structure.heritage(rng, parents)
    first, last, name_heritage = structure.names(rng, sex_code, age, background, heritage, county_code, municipality["municipality_code"])
    first, last = tidy_name(first), tidy_name(last)
    name = f"{first} {last}"
    pron, poss = PRONOUN[sex_code], POSSESSIVE[sex_code]
    marital_code = cell["marital_code"]
    edu_code, edu = education(rng, structure, county_code, age, sex_code)
    status, occupation_code, occupation, sector = employment(rng, structure, county_code, age, sex_code, edu_code, birth_region(birth))
    house = household(rng, age, marital_code)
    place, county = municipality["municipality"], cell["county"]
    outdoors, dish, landmark = REGION[county_code]
    quirks = rng.sample(QUIRKS, 2)
    working = status in ("anställd", "egenföretagare")
    ocean = [int(round(min(80, max(20, rng.gauss(50, 10))))) for _ in range(5)]

    # hobbies / sports / arts / travel pools by life stage
    if age < 6:
        hobbies, sports, arts, travel = HOBBIES_CHILD, SPORTS_CHILD, ARTS_CHILD, TRAVEL_CHILD
    elif age < 16:
        hobbies, sports, arts, travel = HOBBIES_YOUTH, SPORTS_CHILD, ARTS_CHILD, TRAVEL_CHILD
    elif age < 65:
        hobbies, sports, arts, travel = HOBBIES_ADULT, SPORTS_ADULT, ARTS_ADULT, TRAVEL_ADULT
    else:
        hobbies, sports, arts, travel = HOBBIES_ADULT, SPORTS_SENIOR, ARTS_ADULT, TRAVEL_SENIOR
    hobby_list = rng.sample(hobbies, 4 if age >= 6 else 3)
    sport = rng.choice(sports)
    art = rng.choice(arts)
    trip = rng.choice(travel)
    staple = rng.choice(CULINARY_STAPLES)
    cook_style = rng.choice(CULINARY_STYLE)
    value = rng.choice(CULTURE_VALUES)

    # --- cultural background
    if background == "4":
        origin = f"{first} är född i Sverige av föräldrar från {parents} och uppvuxen i {place}"
    elif birth == "Sverige":
        origin = rng.choice((f"{first} är uppvuxen i trakten av {place}", f"{first} växte upp i {county}", f"{first} har rötter i {county} sedan flera generationer"))
    else:
        origin = f"{first} är född i {birth} och har sedan flytten till Sverige gjort {place} till sitt hem"
    cultural = f"{origin}. I vardagen märks {value}, och det lokala livet i {county} präglas av {landmark}."
    if age < 6:
        cultural = f"{first} växer upp i {place} i {county}. Familjen firar högtider som midsommar och lucia och tillbringar mycket tid utomhus. {first} {house}."

    # --- professional
    if age < 6:
        prof = f"{name} är ett förskolebarn i {place} som lär sig genom lek, sång och mycket tid utomhus."
        skills_text = f"{first} övar på att prata, dela med sig och vara nyfiken på omvärlden."
        skills_list = ["språkutveckling", "lek", "motorik"]
        goals = f"{first} är för ung för att ha yrkesplaner men tycker om att leka att {pron} är brandman eller veterinär."
    elif age < 16:
        prof = f"{name} går i grundskolan i {place} och är en nyfiken elev som gärna lär sig genom praktiska uppgifter."
        skills_text = f"{first} är på väg att bli säker på läsning och räkning och är duktig på {hobby_list[0]}."
        skills_list = ["läsning", "samarbete", hobby_list[0]]
        goals = f"{first} funderar redan på vad {pron} vill bli och drömmer om ett yrke kopplat till {hobby_list[1]}."
    elif working:
        years = max(1, age - WORK_START[edu_code])
        group = lower_first(occupation)
        role = "driver eget företag" if status == "egenföretagare" else "arbetar"
        prof = f"{name} {role} i {place} inom yrkesgruppen {group}" + (f", i branschen {sector}." if sector else ".")
        skills_text = f"{first} har cirka {years} års erfarenhet inom yrkesgruppen {group}."
        skills_list = [group] + ([sector] if sector else [])
        goals = f"{first} {rng.choice(CAREER_GOALS if age >= 25 else CAREER_GOALS_YOUNG)}."
    elif status == "studerande":
        prof = f"{name} studerar i {place} och kombinerar studierna med ett aktivt privatliv."
        skills_text = f"{first} har lärt sig studieteknik, att planera sin tid och att samarbeta i grupp."
        skills_list = ["studieteknik", "tidsplanering", "grupparbete"]
        goals = f"{first} {rng.choice(CAREER_GOALS_YOUNG)}."
    elif status == "pensionär":
        prof = f"{name} är pensionär i {place} och har ett långt arbetsliv bakom sig."
        skills_text = f"{first} bär med sig bred yrkeserfarenhet och praktiska färdigheter, särskilt inom {hobby_list[0]}."
        skills_list = ["livserfarenhet", hobby_list[0], "praktiskt kunnande"]
        goals = f"{first} {rng.choice(CAREER_GOALS_OLD)}."
    else:
        prof = f"{name} är för tillfället {'arbetssökande' if status == 'arbetssökande' else 'utanför arbetskraften'} i {place}."
        skills_text = f"{first} har tidigare erfarenheter och är stark inom {hobby_list[0]} och {hobby_list[1]}."
        skills_list = ["anpassningsförmåga", hobby_list[0], hobby_list[1]]
        goals = f"{first} {rng.choice(CAREER_GOALS)}."

    hobby_text = f"{first} tycker om {join_list(hobby_list)}."
    sports_p = f"{name} {sport}" + (f" och {rng.choice(SPORTS_FOLLOW)}." if age >= 16 else ".")
    arts_p = f"{name} {art}" + (f" och uppskattar kulturen kring {landmark}." if age >= 16 else ".")
    travel_p = f"{name} {trip}" + (f", men trivs också med {outdoors} nära hemmet." if age >= 6 else ".")
    culinary_p = f"{name} {cook_style}, och {staple} är en återkommande favorit; {dish} hör till det lokala som {pron} uppskattar." if age >= 16 else f"{name} gillar {staple} och blir glad av {dish} på helgen."
    persona = f"{name} {quirks[0]} och {quirks[1]}, med {value} som en självklar del av vardagen och {hobby_list[0]} som en fast punkt i veckan i {place}."

    conditions = sample_conditions(rng, health, age, "Man" if sex_code == "1" else "Kvinna")
    uuid = f"{rng.getrandbits(128):032x}"
    return {
        "uuid": uuid,
        "professional_persona": prof,
        "healthcare_persona": healthcare_text(rng, name, first, pron, age, conditions),
        "sports_persona": sports_p,
        "arts_persona": arts_p,
        "travel_persona": travel_p,
        "culinary_persona": culinary_p,
        "persona": persona,
        "cultural_background": cultural,
        "skills_and_expertise": skills_text,
        "skills_and_expertise_list": str(skills_list),
        "hobbies_and_interests": hobby_text,
        "hobbies_and_interests_list": str(hobby_list),
        "career_goals_and_ambitions": goals,
        "sex": "Man" if sex_code == "1" else "Kvinna",
        "age": age,
        "marital_status": MARITAL[marital_code],
        "household_type": house,
        "education_level": edu,
        "occupation": occupation if working else "not_in_workforce",
        "occupation_code": occupation_code,
        "industry": sector,
        "employment_status": status,
        "country_of_birth": birth,
        "background": BACKGROUND[background],
        "kommun": place,
        "lan": county,
        "country": "Sverige",
    }, [{"uuid": uuid, "source": c[0], "code": c[1], "condition": c[2]} for c in conditions], {
        "uuid": uuid, "first_name": first, "last_name": last, "name_heritage": name_heritage,
        "parents_country_of_birth": parents, "birth_year": 2025 - age,
        "openness": ocean[0], "conscientiousness": ocean[1], "extraversion": ocean[2], "agreeableness": ocean[3], "neuroticism": ocean[4],
    }


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
    health = load_health()
    structure = Structure()
    records, condition_rows, seed_rows = [], [], []
    for cell in sampled_cells:
        options = municipalities[cell["county_code"]]
        municipality = rng.choices(options, weights=[int(m["population"]) for m in options], k=1)[0]
        row, conditions, seeds = build_row(rng, health, structure, cell, municipality)
        records.append(row)
        seed_rows.append(seeds)
        condition_rows.extend(conditions)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records, schema=SCHEMA), output, compression="zstd")
    pq.write_table(pa.Table.from_pylist(condition_rows, schema=CONDITION_SCHEMA), output.with_name(output.stem + "_conditions.parquet"), compression="zstd")
    pq.write_table(pa.Table.from_pylist(seed_rows, schema=SEED_SCHEMA), output.with_name(output.stem + "_seeds.parquet"), compression="zstd")
    report = {
        "rows": len(records), "seed": seed, "source_year": 2025, "schema": "Nemotron-Personas (nvidia/Nemotron-Personas-France columns; kommun/lan replace commune/departement)",
        "county_counts": dict(Counter(row["lan"] for row in records)),
        "sex_counts": dict(Counter(row["sex"] for row in records)),
        "conditions_rows": len(condition_rows), "note": "SCB-weighted: joint county/age/sex/marital status; municipality by county totals. Names, background, country of birth, education, employment and occupation are sampled from SCB tables (see src/structure.py). Health conditions keep the Socialstyrelsen and Folkhälsomyndigheten age/sex rates, with assumed within-cluster correlation. Household type and all text fields are rule-based placeholders, not LLM generated."
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
