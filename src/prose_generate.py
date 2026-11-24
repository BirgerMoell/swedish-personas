"""Write the persona texts and work profiles with a language model behind an OpenAI-compatible API.

Usage: python3 src/prose_generate.py SEEDS.jsonl OUT.jsonl --taxonomy ssyk4.json --catalogue tasks.jsonl
                                     --url http://127.0.0.1:8000/v1 [--workers 48]

Steps
  1. Task catalogue: for every occupation group (SSYK 4-digit) among the seeds, the model lists the
     group's main work tasks from the official description, job titles and skills (JobTech Taxonomy).
  2. Work profile, for each working persona: a job title, a workplace and the tasks this person does,
     chosen from the catalogue by id.
  3. Attributes (background, skills, interests, goals) and 4. persona portraits, as in Nemotron-Personas.

Standard library only, so it runs inside any serving container. Resumable: finished work is skipped.
"""

import argparse
import json
import re
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SYSTEM = """Du skriver personporträtt till en syntetisk datamängd över Sveriges befolkning. Varje porträtt ska läsas som en verklig, enskild människa och inte som ett genomsnitt.

Regler:
- Skriv naturlig, vardaglig och korrekt svenska i tredje person och löpande text. Inga listor i textfälten. Kontrollera stavningen, också av ortnamn.
- Personens förnamn eller hela namn ska finnas med i varje textfält. Varje fält har en anvisning om hur första meningen ska inledas: följ den.
- Uppgifterna du får är fakta. Ändra inte ålder, bostadsort, utbildning, yrke, civilstånd, hushåll eller födelseland och hitta inte på något som säger emot dem.
- Var konkret och specifik: verkliga platser, namngivna föreningar, bestämda rätter, vanor och detaljer som passar just den här personen, orten och generationen. Två personer ska inte kunna byta text med varandra.
- Ursprung ska märkas i det personen gör, till exempel språk hemma, mat, högtider, släktkontakter och resor, och inte bara konstateras. Välj inte det mest kända från ett land; välj det vardagliga och personliga. Många med utländsk bakgrund lever ett helt vanligt svenskt vardagsliv och det ska också få synas.
- Undvik slitna Sverigeklichéer (fika, lagom, midsommar, allemansrätten, Jantelagen, köttbullar) om de inte verkligen betyder något särskilt för personen.
- Promenader, matlagning och "socialt umgänge" är inga intressen i sig. Skriv inte "husmanskost": nämn rätterna.
- Använd inte de här uttrycken: "expert på", "skicklig på att", "spenderar", "när det kommer till", "består främst av", "är känd för att", "främsta mål", "sina rötter", "ser till att", "balanserar", "med glimten i ögat".
- Personlighetsdragen ska visa sig i beteende och val. Nämn inte dragen som etiketter.
- Anpassa allt efter åldern. Små barn beskrivs genom lek, förskola och familj. Skolbarn har inga yrkesplaner utöver drömmar. Pensionärer har ett tidigare arbetsliv som passar utbildningen.
- Hälsa: nämn bara de besvär som anges. Finns inga angivna, hitta inte på diagnoser. Alla går inte till vårdcentralen: variera hur kontakten med vården ser ut.
- Svara endast med JSON enligt schemat."""

WORK_SYSTEM = """Du beskriver arbetsuppgifter i svenska yrken till en datamängd som ska användas för att bygga realistiska övningsuppgifter för AI-system. Var saklig, konkret och korrekt. Skriv på svenska. Svara endast med JSON enligt schemat."""

ATTRIBUTES = {
    "cultural_background": "3-5 meningar om uppväxt, familj, språk, traditioner och hur orten och ursprunget har format personen.",
    "skills_and_expertise": "2-4 meningar om vad personen kan, från arbete, utbildning och livet i övrigt.",
    "skills_and_expertise_list": "3-6 korta, specifika färdigheter som nämns eller följer av texten.",
    "hobbies_and_interests": "2-4 meningar om vad personen gör på fritiden, med konkreta detaljer.",
    "hobbies_and_interests_list": "3-6 korta, specifika intressen som nämns eller följer av texten.",
    "career_goals_and_ambitions": "2-3 meningar om mål och planer för arbete, studier eller livet framåt, rimliga för åldern.",
}
PERSONAS = {
    "professional_persona": "2-3 meningar om personen i arbetet, skolan eller motsvarande vardag.",
    "sports_persona": "2 meningar om motion, idrott och lag eller föreningar personen följer eller är med i, eller varför inte.",
    "arts_persona": "2 meningar om kultur: musik, böcker, film, hantverk eller scen.",
    "travel_persona": "2 meningar om hur och vart personen reser.",
    "culinary_persona": "2 meningar om mat: vad som lagas hemma, favoriter och vanor.",
    "healthcare_persona": "2-3 meningar om hälsa och hur personen förhåller sig till vården.",
    "persona": "1-2 meningar som sammanfattar personen som helhet. Börja inte med \"<namn> är en\".",
}
LISTS = ("skills_and_expertise_list", "hobbies_and_interests_list")
BANNED = ("yrkesgrupp", "expert på", "skicklig på att", "spenderar", "när det kommer till", "består främst av", "husmanskost")
COMPUTER = ("helt", "delvis", "nej")
SENIORITY = ("ny i yrket", "några års erfarenhet", "erfaren", "mycket erfaren", "arbetsledande")
TEXT = {"type": "string"}


def strings(low, high):
    return {"type": "array", "items": TEXT, "minItems": low, "maxItems": high}


def obj(props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def prose_schema(fields):
    return obj({name: strings(3, 6) if name in LISTS else TEXT for name in fields})


CATALOGUE_SCHEMA = obj({"tasks": {"type": "array", "minItems": 8, "maxItems": 12, "items": obj({
    "task": TEXT, "computer_based": {"type": "string", "enum": list(COMPUTER)}, "tools": strings(1, 5), "output": TEXT})}})


def profile_schema(task_ids, titles):
    return obj({
        "job_title": TEXT, "workplace": TEXT, "seniority": {"type": "string", "enum": list(SENIORITY)},
        "tasks": {"type": "array", "minItems": 4, "maxItems": 7, "items": obj({
            "task_id": {"type": "string", "enum": task_ids}, "share_percent": {"type": "integer", "minimum": 5, "maximum": 70}, "detail": TEXT})},
        "tools": strings(2, 8),
    })


class Client:
    def __init__(self, url, temperature):
        self.url = url.rstrip("/")
        self.temperature = temperature
        self.model = json.load(urllib.request.urlopen(self.url + "/models"))["data"][0]["id"]

    def ask(self, system, user, schema, seed, temperature=None):
        body = {
            "model": self.model, "temperature": self.temperature if temperature is None else temperature, "top_p": 0.95,
            "max_tokens": 2200, "seed": seed, "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "reply", "schema": schema}},
        }
        request = urllib.request.Request(self.url + "/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            reply = json.load(urllib.request.urlopen(request, timeout=900))
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:300]}")
        text = reply["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", text, flags=re.S)
        return json.loads(match.group(0) if match else text), reply["usage"]["completion_tokens"]

    def attempt(self, system, user, schema, seed, check, attempts=4, temperature=None):
        """Ask until check(result) returns no problems. Returns (result or None, tokens, retries, problems)."""
        tokens, last = 0, None
        for n in range(attempts):
            try:
                result, used = self.ask(system, user, schema, seed + n, temperature)
                tokens += used
                last = check(result)
                if n >= 2:  # style slips are only worth two retries
                    last = [x for x in last if ": says '" not in x]
            except Exception as error:  # bad JSON, timeout, server error
                result, last = None, [f"error: {error}"]
            if not last:
                return result, tokens, n, []
        return None, tokens, attempts, last


def group(taxonomy, code):
    """Official text for an occupation group. SCB splits manager groups by level (1211, 1212) where the
    taxonomy has one group (1210), and a few groups differ in the last digit."""
    for key in (code, code[:3] + "0"):
        if key in taxonomy:
            return taxonomy[key]
    near = sorted(k for k in taxonomy if k[:3] == code[:3])
    return taxonomy[near[0]] if near else {"label": "", "definition": "", "titles": [], "skills": []}


def build_catalogue(client, seeds, taxonomy, path, workers):
    """One list of tasks per occupation group; ids are '<ssyk>-<nn>'."""
    catalogue = {}
    try:
        for row in map(json.loads, open(path, encoding="utf-8")):
            catalogue[row["occupation_code"]] = row
    except FileNotFoundError:
        pass
    labels = {s["occupation_code"]: s["occupation"] for s in seeds if s["occupation_code"]}
    todo = sorted(set(labels) - set(catalogue))
    lock = threading.Lock()

    def check(result):
        tasks = result.get("tasks", [])
        if len({t["task"] for t in tasks}) != len(tasks):
            return ["duplicate tasks"]
        return [f"short task: {t['task']}" for t in tasks if len(t["task"].split()) < 4]

    def run(code):
        official = group(taxonomy, code)
        user = (f"Yrkesgrupp (SSYK {code}): {labels[code]}\nOfficiell beskrivning: {official['definition'] or 'saknas'}\n"
                f"Yrkestitlar i gruppen: {', '.join(official['titles'][:40]) or 'saknas'}\n"
                f"Kompetenser som efterfrågas: {', '.join(official['skills'][:60]) or 'saknas'}\n\n"
                "Lista 8-12 arbetsuppgifter som tillsammans täcker det mesta av arbetstiden i yrkesgruppen i Sverige i dag. För varje uppgift:\n"
                "- task: en mening som börjar med ett verb och säger vad som görs, med vad och för vem.\n"
                "- computer_based: \"helt\" om uppgiften i sin helhet utförs vid en dator, \"delvis\" om en väsentlig del gör det, annars \"nej\".\n"
                "- tools: de verktyg, system, maskiner eller dokument som används. Namnge typiska svenska system där det är rimligt.\n"
                "- output: vad uppgiften lämnar efter sig, till exempel ett dokument, ett beslut, en registrering eller ett utfört arbete.\n"
                "Ta med både kärnuppgifter och det administrativa runt omkring. Hitta inte på uppgifter som yrkesgruppen inte har.")
        result, tokens, retries, problems = client.attempt(WORK_SYSTEM, user, CATALOGUE_SCHEMA, int(code), check, temperature=0.4)
        if problems:
            print("catalogue failed", code, problems, flush=True)
            return
        row = {"occupation_code": code, "occupation": labels[code], "source": "model-written from JobTech Taxonomy text",
               "tasks": [dict(task_id=f"{code}-{i + 1:02d}", **t) for i, t in enumerate(result["tasks"])], "completion_tokens": tokens}
        with lock:
            catalogue[code] = row
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()

    with open(path, "a", encoding="utf-8") as handle, ThreadPoolExecutor(workers) as pool:
        list(pool.map(run, todo))
    print(f"catalogue: {len(catalogue)} occupation groups ({len(todo)} new)", flush=True)
    return catalogue


def facts(seed, work=None):
    lines = [
        f"Namn: {seed['first_name']} {seed['last_name']}",
        f"Kön: {seed['sex']}",
        f"Ålder: {seed['age']} år (född {seed['birth_year']})",
        f"Bor i: {seed['kommun']} kommun ({seed['lan']})",
        f"Födelseland: {seed['country_of_birth']}",
        f"Bakgrund: {seed['background']}",
    ]
    if seed["parents_country_of_birth"] != seed["country_of_birth"]:
        lines.append(f"Föräldrarnas födelseland: {seed['parents_country_of_birth']}")
    lines += [
        f"Civilstånd: {seed['marital_status']}",
        f"Hushåll: {seed['household_type']}",
        f"Utbildning: {seed['education_level']}",
        f"Sysselsättning: {seed['employment_status']}",
    ]
    if seed["occupation_code"]:
        lines.append(f"Yrkesområde: {seed['occupation']}, bransch {seed['industry']}")
    if work:
        lines.append(f"Yrkestitel: {work['job_title']} ({work['seniority']})")
        lines.append(f"Arbetsplats: {work['workplace']}")
        lines.append("Arbetsuppgifter: " + "; ".join(t["detail"] for t in work["tasks"][:4]))
    lines.append("Hälsobesvär: " + (", ".join(seed["conditions"]) if seed["conditions"] else "inga angivna"))
    if seed.get("health_contact"):
        lines.append("Kontakt med vården (utgå från detta): " + seed["health_contact"])
    lines.append("Personlighet (anpassa efter åldern): " + "; ".join(seed["personality"]))
    return "\n".join(lines)


def describe(fields, seed):
    out = []
    for name, text in fields.items():
        if name in LISTS:
            out.append(f"- {name}: {text}")
        else:
            out.append(f"- {name}: {text} Inled första meningen {seed['openings'][name]}.")
    return "\n".join(out)


def prose_problems(result, fields, seed):
    found, unnamed = [], []
    for name in fields:
        value = result.get(name)
        if name in LISTS:
            if not isinstance(value, list) or not 3 <= len(value) <= 6 or not all(isinstance(v, str) and v.strip() for v in value):
                found.append(f"{name}: bad list")
            continue
        if not isinstance(value, str) or len(value.split()) < 8:
            found.append(f"{name}: missing or too short")
        else:
            if seed["first_name"] not in value and seed["last_name"] not in value:
                unnamed.append(name)
            found += [f"{name}: says '{b}'" for b in BANNED if b in value.lower()]
    # Pilot 2 rejected 1.3% of personas because one field used a pronoun instead of the name.
    # That reads naturally, so only a text that mostly leaves the name out is retried.
    if len(unnamed) > 2:
        found.append(f"name missing in {', '.join(unnamed)}")
    return found


def work_profile(client, seed, catalogue, taxonomy, base):
    entry = catalogue.get(seed["occupation_code"])
    if not entry:
        return None, 0, 0, ["no catalogue for occupation"]
    ids = [t["task_id"] for t in entry["tasks"]]
    titles = group(taxonomy, seed["occupation_code"])["titles"]
    user = (f"Person: {seed['first_name']} {seed['last_name']}, {seed['sex'].lower()}, {seed['age']} år, bor i {seed['kommun']} kommun ({seed['lan']}).\n"
            f"Utbildning: {seed['education_level']}\nSysselsättning: {seed['employment_status']}\n"
            f"Yrkesgrupp (SSYK {seed['occupation_code']}): {seed['occupation']}\nBransch: {seed['industry']}\n"
            f"Yrkestitlar i gruppen: {', '.join(titles[:40]) or 'saknas'}\n\nUppgifter i yrkesgruppen:\n"
            + "\n".join(f"{t['task_id']}: {t['task']}" for t in entry["tasks"])
            + "\n\nBeskriv den här personens arbete:\n"
            "- job_title: en konkret yrkestitel, helst en av titlarna ovan, som passar ålder, utbildning och bransch.\n"
            "- workplace: typ av arbetsplats och ungefärlig storlek, rimlig för kommunen. Använd inte verkliga företagsnamn; offentliga arbetsgivare som en region eller kommun får nämnas.\n"
            "- seniority: rimlig för åldern.\n"
            "- tasks: de 4-7 uppgifter ur listan som personen faktiskt gör en vanlig vecka. share_percent är andelen av arbetstiden och ska summera till 100. detail är en mening om hur just den här personen gör uppgiften på sin arbetsplats.\n"
            "- tools: de system, verktyg eller maskiner personen använder mest.\n"
            "Olika personer i samma yrkesgrupp har olika tyngdpunkt: välj en tydlig inriktning.")

    def check(result):
        picked = [t["task_id"] for t in result.get("tasks", [])]
        found = []
        if len(set(picked)) != len(picked) or not set(picked) <= set(ids):
            found.append("bad task ids")
        if not 60 <= sum(t["share_percent"] for t in result.get("tasks", [])) <= 140:
            found.append("shares do not sum to about 100")
        if len(result.get("job_title", "").strip()) < 3 or "yrkesgrupp" in result.get("job_title", "").lower():
            found.append("bad job title")
        return found

    result, tokens, retries, problems = client.attempt(WORK_SYSTEM, user, profile_schema(ids, titles), base + 100, check)
    if problems:
        return None, tokens, retries, problems
    total = sum(t["share_percent"] for t in result["tasks"])
    for t in result["tasks"]:  # rescale so that the shares sum to exactly 100
        t["share_percent"] = round(100 * t["share_percent"] / total)
    result["tasks"].sort(key=lambda t: -t["share_percent"])
    result["tasks"][0]["share_percent"] += 100 - sum(t["share_percent"] for t in result["tasks"])
    return result, tokens, retries, []


def write_one(client, seed, catalogue, taxonomy):
    base = int(seed["uuid"][:8], 16)
    out = {"uuid": seed["uuid"]}
    tokens = retries = 0
    work = None
    if seed["occupation_code"]:
        work, used, again, problems = work_profile(client, seed, catalogue, taxonomy, base)
        tokens, retries = tokens + used, retries + again
        if problems:
            return {"uuid": seed["uuid"], "failed": ["work: " + p for p in problems]}
        out["work"] = work
    info = facts(seed, work)
    ideas = "Uppslag till fritidsintressen (välj högst två som passar, eller andra lika specifika): " + ", ".join(seed["leisure_ideas"])
    steps = (
        (ATTRIBUTES, lambda: f"Uppgifter om personen:\n{info}\n{ideas}\n\nSkriv följande fält:\n{describe(ATTRIBUTES, seed)}"),
        (PERSONAS, lambda: f"Uppgifter om personen:\n{info}\n\nRedan skrivet om personen:\n"
                           + "\n".join(f"{k}: {out[k]}" for k in ATTRIBUTES if k not in LISTS)
                           + "\n\nSkriv följande fält. De ska stämma med det som redan är skrivet men tillföra nya detaljer och inte upprepa det:\n"
                           + describe(PERSONAS, seed)),
    )
    for fields, prompt in steps:
        result, used, again, problems = client.attempt(SYSTEM, prompt(), prose_schema(fields), base, lambda r: prose_problems(r, fields, seed))
        tokens, retries = tokens + used, retries + again
        if problems:
            return {"uuid": seed["uuid"], "failed": problems}
        for name in fields:
            out[name] = [v.strip() for v in result[name]] if name in LISTS else " ".join(result[name].split())
    out["completion_tokens"], out["retries"] = tokens, retries
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seeds")
    ap.add_argument("out")
    ap.add_argument("--taxonomy", required=True)
    ap.add_argument("--catalogue", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--workers", type=int, default=48)
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--shard", help="K/N: write only every N-th persona, starting at K (0-based), so N jobs can split the data")
    ap.add_argument("--catalogue-only", action="store_true", help="write the task catalogue and stop")
    args = ap.parse_args()
    seeds = [json.loads(line) for line in open(args.seeds, encoding="utf-8")]
    catalogue_seeds = seeds  # the catalogue always covers every group, whatever the shard
    if args.shard:
        k, n = map(int, args.shard.split("/"))
        seeds = seeds[k::n]
    seeds = seeds[:args.limit]
    taxonomy = json.load(open(args.taxonomy, encoding="utf-8"))
    done = set()
    try:
        done = {r["uuid"] for r in map(json.loads, open(args.out, encoding="utf-8")) if "failed" not in r}
    except FileNotFoundError:
        pass
    todo = [s for s in seeds if s["uuid"] not in done]
    client = Client(args.url, args.temperature)
    print(f"model {client.model}: {len(todo)} to write, {len(done)} already done", flush=True)
    catalogue = build_catalogue(client, catalogue_seeds, taxonomy, args.catalogue, args.workers)
    if args.catalogue_only:
        return
    lock = threading.Lock()
    count = {"ok": 0, "failed": 0, "tokens": 0, "retries": 0}
    with open(args.out, "a", encoding="utf-8") as handle:
        def run(seed):
            try:
                row = write_one(client, seed, catalogue, taxonomy)
            except Exception as error:
                row = {"uuid": seed["uuid"], "failed": [f"crash: {error!r}"]}
            with lock:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                count["failed" if "failed" in row else "ok"] += 1
                count["tokens"] += row.get("completion_tokens", 0)
                count["retries"] += row.get("retries", 0)
                if (count["ok"] + count["failed"]) % 50 == 0:
                    print(count, flush=True)
        with ThreadPoolExecutor(args.workers) as pool:
            list(pool.map(run, todo))
    print("finished", count, flush=True)


if __name__ == "__main__":
    main()
