---
pretty_name: Swedish Personas v2 (preview)
language:
- sv
license: cc-by-4.0
task_categories:
- text-generation
size_categories:
- 100K<n<1M
annotations_creators:
- machine-generated
language_creators:
- machine-generated
multilinguality:
- monolingual
source_datasets:
- original
tags:
- synthetic
- personas
- nemotron-personas
- swedish
- sweden
- demographics
- occupations
- work-tasks
- ssyk
- scb
configs:
- config_name: pilot
  default: true
  data_files:
  - split: train
    path: data/pilot.parquet
- config_name: task_catalogue
  data_files:
  - split: train
    path: data/task_catalogue.parquet
- config_name: personas_100k
  data_files:
  - split: train
    path: data/personas_100k.parquet
- config_name: seeds_100k
  data_files:
  - split: train
    path: data/seeds_100k.parquet
- config_name: conditions_100k
  data_files:
  - split: train
    path: data/conditions_100k.parquet
---

# Swedish Personas v2 (preview)

**Sverige, en person i taget.** Synthetic Swedish personas in the [Nemotron-Personas](https://docs.nvidia.com/nemo/datadesigner/dev-notes/designing-nemotron-personas) format, rebuilt after an external quality review of [v1](https://huggingface.co/datasets/birgermoell/swedish-personas).

This is a work-in-progress preview, not a finished release. It holds two things:

- **A structured layer for 100,000 personas**, sampled from Statistics Sweden (SCB) tables: names, country of birth, parents' birthplace, education, employment and occupation now depend on each other and on county, age and sex.
- **A 987-persona pilot** where a language model (Gemma 4 31B) wrote the Swedish text from that structured layer, plus a **work profile** per working persona that links to a **catalogue of 2,004 work tasks** in 197 occupation groups.

The full 100,000 personas with model-written text have not been generated yet.

Code: [github.com/RenaissanceLabs-EU/swedish-personas](https://github.com/RenaissanceLabs-EU/swedish-personas)

## At a glance

| Config | Rows | What it is | Text written by |
|---|---|---|---|
| `pilot` (default) | 987 | Persona, name, structured fields, 11 text fields, work profile | Gemma 4 31B |
| `task_catalogue` | 2,004 | Work tasks per occupation group, with a computer-based flag | Gemma 4 31B, from official occupation text |
| `personas_100k` | 100,000 | Structured layer in the Nemotron column layout | v1 templates (placeholder) |
| `seeds_100k` | 100,000 | Name, name heritage, parents' birthplace, birth year, Big Five scores | sampled |
| `conditions_100k` | 143,786 | Health conditions per persona | sampled |

All configs join on `uuid`.

## Quick start

```python
from datasets import load_dataset

repo = "RenaissanceLabsEU/swedish-personas-v2"

pilot = load_dataset(repo, "pilot", split="train")
p = pilot[0]
print(p["first_name"], p["last_name"], p["age"], p["kommun"])
print(p["persona"])

# Working personas and what they do in a week
workers = pilot.filter(lambda r: r["job_title"] is not None)
for task in workers[0]["work_tasks"]:
    print(task["share_percent"], task["computer_based"], task["task"])

# Tasks done fully at a computer, across occupations
tasks = load_dataset(repo, "task_catalogue", split="train")
desk = tasks.filter(lambda t: t["computer_based"] == "helt")

# The 100,000-persona structured layer
people = load_dataset(repo, "personas_100k", split="train")
seeds = load_dataset(repo, "seeds_100k", split="train")
```

## A pilot persona

Shortened; every record has all the fields listed further down.

```json
{
  "first_name": "Mohamed", "last_name": "Hanna",
  "sex": "Man", "age": 48, "kommun": "Västerås", "lan": "Västmanland",
  "country_of_birth": "Sverige",
  "background": "inrikes född med två utrikes födda föräldrar",
  "parents_country_of_birth": "Irak",
  "education_level": "eftergymnasial utbildning, mindre än 3 år",
  "occupation": "Träarbetare, snickare m.fl.", "occupation_code": "7111",
  "conditions": ["förmaksflimmer", "högt blodtryck", "svår värk i rörelseorganen"],

  "cultural_background": "Mohamed Hanna växte upp i Västerås där han tidigt blev bryggan mellan föräldrarnas irakiska bakgrund och det svenska samhället. Hemma talades både svenska och arabiska, och han minns doften av dolma och bryggt kaffe under långa familjemiddagar. ...",
  "professional_persona": "När Mohamed Hanna kliver in på byggarbetsplatsen i Västerås börjar han alltid med att stämma av veckans materialleveranser mot ritningarna. ...",
  "hobbies_and_interests": "Att skruva på en gammal Volvo från sjuttiotalet i garaget är det som får Mohamed Hanna att koppla av efter arbetsveckan. ...",
  "healthcare_persona": "Trots att värken i kroppen ofta begränsar rörligheten går Mohamed Hanna sällan till läkaren utan väntar tills besvären blir ohållbara. ...",

  "job_title": "Snickare",
  "workplace": "Medelstort byggföretag specialiserat på bostadsrenoveringar och nyproduktion i Västerås",
  "seniority": "erfaren",
  "work_tools": ["Kapsåg", "Spikpistol", "Laserpass", "Digitalt tidrapporteringssystem", "Skruvdragare"],
  "work_tasks": [
    {"task_id": "7111-02", "share_percent": 30, "computer_based": "nej",
     "task": "Montera innerväggar, isolering och beklädnad för bostäder eller lokaler.",
     "detail": "Mohamed monterar regelverk och isolerar väggar i samband med ombyggnation av äldre lägenheter."},
    {"task_id": "7111-09", "share_percent": 10, "computer_based": "delvis",
     "task": "Läsa och tolka tekniska ritningar för att planera materialåtgång och utförande.",
     "detail": "Han analyserar arkitektritningar för att beräkna exakt mängd virke inför veckans projekt."},
    {"task_id": "7111-10", "share_percent": 10, "computer_based": "helt",
     "task": "Dokumentera utfört arbete och rapportera tid samt materialåtgång i projektledningssystem.",
     "detail": "Han registrerar sina arbetstimmar och materialförbrukning digitalt i företagets projektverktyg."}
  ]
}
```

## Why v2

An external review of v1 (November 2026) found that the demographic spine was correct but that the rest was templated and unconditioned. The table shows the review's measures, recomputed with `src/metrics.py`. The first two columns are on 100,000 personas; the pilot column is on 987.

| Measure | v1 | v2 structured layer | v2 pilot |
|---|---|---|---|
| Distinct given names / surnames | 40 / 40 | 3,734 / 13,034 | same layer |
| Distinct full names | 1,600 | 81,976 | same layer |
| Share held by the ten commonest surnames | 25.5% | 15.5% | same layer |
| Occupation vs education (Cramér's V) | 0.10 | 0.37 | same layer |
| Nurses with compulsory school only | 14.8% | 0% | same layer |
| Distinct occupations | 36 | 428 | same layer |
| County vs education (Cramér's V) | 0.017 | 0.071 | same layer |
| County vs occupation (Cramér's V) | 0.028 | 0.119 | same layer |
| Diabetes with high blood pressure, age- and sex-adjusted lift | 0.99 | 1.45 | same layer |
| Anxiety with depression, age- and sex-adjusted lift | 0.99 | 5.32 | same layer |
| Five-word overlap between two personas, `persona` field | 14.3% | 14.4% (templates) | 0.04% |
| Top-3 openings share, `cultural_background` | 75.1% | 71.5% (templates) | 28.7% |
| Top-3 openings share, worst other text field | 41.9% | 42.7% (templates) | 19.4% |

The surname share is higher than in comparable datasets from other countries because it matches Sweden: the ten commonest surnames cover 15.1% of SCB's surname table. Full metric files are in `reports/`.

## How it was made

### 1. Structured layer (no language model)

Each persona starts from a cell in SCB's joint distribution of county, age, sex and marital status (table 000007ME, 2025), as in v1. v2 then samples, in order:

| Field | Depends on | SCB source |
|---|---|---|
| Background (Swedish or foreign, by parents' birthplace) | county, age, sex | Foreign/Swedish background by region, age and sex, 2025 |
| Country of birth | county, age, sex | Population by country of birth, by region and by age, 2025 |
| Name heritage | country of birth (or parents') | hand-written mapping, see limits |
| Given name | sex, birth year, heritage | Given names 2020, mean age per name, top 100 by birth year 1922–2021, newborn names 1998–2022 |
| Surname | heritage | Surnames 2020 |
| Education | county, age, sex | Education level by region, age and sex, 2025 |
| Employment | county, age, sex, education | Employees by region, occupation, age and sex, 2024 |
| Occupation (SSYK 2012, four digits) and industry | county, age, sex, education, region of birth | Occupation register, 2024 |
| Health conditions | age, sex, plus a shared factor per cluster | Socialstyrelsen and Folkhälsomyndigheten, 2024 |
| Big Five scores | independent, mean 50, sd 10 | none, as in Nemotron-Personas |

Tables with different conditioning variables are combined by multiplying a base distribution with ratios from the others (a naive-Bayes style adjustment). Licensed health and teaching occupations require post-secondary education. Health conditions keep v1's age- and sex-specific rates, and a one-factor Gaussian copula per cluster (cardiometabolic, mental health, pain, atopic) makes related conditions co-occur.

Validation (`src/validate.py`) compares the sample with national SCB totals. Total variation distance: background 0.001, country of birth among the foreign-born 0.025, education 0.005, occupation major group 0.019. 20.9% of the personas are foreign-born.

### 2. Model-written text (pilot)

Following the Nemotron-Personas recipe, the model gets the structured record and writes in structured calls:

1. **Work profile** (working personas only): job title, workplace, seniority, tools, and 4–7 tasks chosen by id from the task catalogue with a share of the working week.
2. **Attributes**: cultural background, skills, interests, goals.
3. **Persona portraits**: professional, sports, arts, travel, culinary, healthcare and a summary, written to agree with step 2.

Personality scores are given to the model as plain descriptions, not numbers. Each text field is assigned one of seven ways to open its first sentence, a set of stock phrases is banned, and each persona is shown twelve leisure ideas drawn from a list to choose from. Without those three measures the first pilot opened 74% of cultural backgrounds with the same four words.

Replies are checked and retried: every text field must contain the person's name, lists must have 3–6 items, task ids must exist in the catalogue. 13 of 1,000 personas failed after four attempts and are left out.

Model: `google/gemma-4-31B-it` served with vLLM on two H200 GPUs on the Berzelius cluster (NSC, Linköping), temperature 0.9, top-p 0.95, schema-constrained JSON. About 1.3 million output tokens in 19 minutes for the pilot including the catalogue.

### 3. Task catalogue

The purpose is to make the personas usable for building work-like training environments: pick tasks that many people actually do, then sample personas who do them.

For each of the 197 occupation groups in the pilot, the model was given the official description, the job titles and the requested skills from Arbetsförmedlingen's [JobTech Taxonomy](https://taxonomy.api.jobtechdev.se/), and asked for 8–12 tasks that cover most of the working time in the group. Each task has:

- `task`: one sentence starting with a verb
- `computer_based`: `helt` (done entirely at a computer), `delvis` (a substantial part is), `nej`
- `tools`: systems, machines or documents used
- `output`: what the task leaves behind

Of the 2,004 tasks, 587 are `helt`, 787 `delvis` and 630 `nej`. Weighted by the time shares in the 510 work profiles, 26% of working time goes to `helt` tasks and 33% to `delvis` tasks.

## Fields

### `pilot`

| Column | What it holds |
|---|---|
| `uuid` | Persona id, shared across configs |
| `first_name`, `last_name` | Sampled from SCB name tables |
| `sex`, `age`, `marital_status` | From SCB's joint distribution; `sex` is registered binary sex, `age=100` means 100 or older |
| `household_type` | Rule-based from age and marital status (unchanged from v1) |
| `education_level` | SCB level (SUN 2020), or the current school stage for children |
| `occupation`, `occupation_code`, `industry` | SSYK 2012 four-digit group and industry; `not_in_workforce` and empty when not working |
| `employment_status` | `anställd`, `egenföretagare`, `arbetssökande`, `studerande`, `elev`, `barn`, `pensionär`, `utanför arbetskraften` |
| `country_of_birth`, `background`, `parents_country_of_birth` | Birthplace and SCB's four background groups |
| `kommun`, `lan`, `country` | Municipality, county, `Sverige` |
| `name_heritage` | Group the name was drawn from: SV, FI, WEU, EEU, BALK, TR, AR, IR, HOA, SAS, EAS, LAT, AFR |
| `birth_year` | 2025 minus age |
| `openness`, `conscientiousness`, `extraversion`, `agreeableness`, `neuroticism` | Big Five T-scores, 20–80 |
| `conditions` | List of sampled health conditions |
| `persona`, `cultural_background`, `professional_persona`, `skills_and_expertise`, `hobbies_and_interests`, `career_goals_and_ambitions`, `sports_persona`, `arts_persona`, `travel_persona`, `culinary_persona`, `healthcare_persona` | Model-written Swedish text |
| `skills_and_expertise_list`, `hobbies_and_interests_list` | Lists of 3–6 short items |
| `job_title`, `workplace`, `seniority`, `work_tools` | Work profile; null for the 477 personas who do not work |
| `work_tasks` | List of `{task_id, share_percent, task, computer_based, detail}`; shares sum to 100 |

### `task_catalogue`

`occupation_code`, `occupation`, `task_id` (`<SSYK code>-<number>`), `task`, `computer_based`, `tools` (list), `output`.

### `personas_100k`, `seeds_100k`, `conditions_100k`

`personas_100k` has the Nemotron column layout plus `occupation_code`, `industry`, `employment_status`, `country_of_birth` and `background`. **Its text columns are still v1 templates** and will be replaced; its list columns are stringified lists, as in Nemotron-Personas. `seeds_100k` holds names, heritage, parents' birthplace, birth year and Big Five scores. `conditions_100k` has one row per persona and condition (`uuid`, `source`, `code`, `condition`).

## Known limits

Read these before relying on the data.

**Structured layer**

- **Name heritage labels are model-made and unchecked.** The 12,000 commonest names were labelled by a language model, which defaulted unknown names to Swedish. A spot check of 150 Swedish-labelled surnames that do not follow Swedish spelling patterns found about eight wrong. Rarer names are left out unless they match a Swedish surname pattern.
- **Names are drawn by broad region, not country.** A person born in Lithuania can get a Polish-sounding surname.
- **The country-to-heritage mapping and the comorbidity strengths are judgement calls**, not statistics. They are marked `ASSUMPTION` in the code.
- **Place signal is at county level.** Municipality is drawn from county population only. Household type is still v1's rule.
- **No modelling of national minorities** (Sami, Tornedalians, Roma, Jews, Sweden Finns beyond the FI name group).
- SCB's cells have disclosure-control noise, and the sample has sampling error.

**Model-written text and work layer**

- **No native-speaker review has been done yet.** Occasional misspellings and invented words occur ("sanningsbrott" for true crime).
- **Tasks, tools and time shares are plausible, not measured.** The catalogue is grounded in official occupation text, but no one has checked it, and some named software systems may not exist.
- **Clichés remain.** "Fika" appears in 17% of pilot personas and "vårdcentral" in 59%. 17% of cultural backgrounds still open with "X växte upp i".
- **Leisure interests reflect a hand-written idea list**, not survey data.
- **Details the structured layer does not fix are the model's choice**, including a partner's gender, children, pets and past jobs for pensioners.
- Heritage is shown through practice as intended, but can lean on the best-known food or holiday of a country.

**Use**

Use for Swedish-language prototyping, test fixtures, persona-conditioned generation and research on synthetic data. Do not use for demographic inference, allocation of public services, or decisions about individuals. The health fields are not for clinical or epidemiological inference. All personas are fictional; with real name tables and real municipalities, a persona can by coincidence share a name and town with a real person.

## Sources and licence

- **Statistics Sweden (SCB)**: population, name, background, education and occupation tables, fetched from the open PxWeb API by `src/fetch_scb.py` and `src/fetch_scb_v2.py`.
- **Socialstyrelsen** (diagnoses in inpatient and specialised outpatient care, 2024) and **Folkhälsomyndigheten** (National Public Health Survey, 2024): health rates.
- **Arbetsförmedlingen, JobTech Taxonomy**: occupation descriptions, job titles and skills used as input for the task catalogue.
- **Gemma 4 31B** (Google): pilot text and task catalogue.
- **Nemotron-Personas** (NVIDIA) and **Nemotron-Personas-Belgium** (Pleias): schema and generation recipe.

Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with attribution to the sources above. Code: MIT.

## Citation

```bibtex
@misc{moell2026swedishpersonasv2,
  title  = {Swedish Personas v2 (preview): synthetic Swedish personas with SCB-conditioned structure, model-written text and work tasks},
  author = {Moell, Birger},
  year   = {2026},
  publisher = {Renaissance Labs},
  url    = {https://huggingface.co/datasets/RenaissanceLabsEU/swedish-personas-v2}
}
```
