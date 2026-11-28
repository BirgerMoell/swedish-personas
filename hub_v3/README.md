---
pretty_name: Swedish Personas v3
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
- config_name: personas_100k
  default: true
  data_files:
  - split: train
    path: data/personas_100k.parquet
- config_name: task_catalogue
  data_files:
  - split: train
    path: data/task_catalogue.parquet
- config_name: conditions_100k
  data_files:
  - split: train
    path: data/conditions_100k.parquet
---
# Swedish Personas v3

*A NAISS dataset: published by the [National Academic Infrastructure for Supercomputing in Sweden](https://huggingface.co/naiss-se).*

**Sverige, en person i taget.** 100,000 synthetic Swedish personas in the [Nemotron-Personas](https://docs.nvidia.com/nemo/datadesigner/dev-notes/designing-nemotron-personas) format. Every person has an SCB-conditioned structured record, eleven Swedish text fields written by a language model (Gemma 4 31B), and, for the 51% who work, a work profile linked to a catalogue of 4,348 work tasks in 428 occupation groups.

v3 is the first release with model-written text for all 100,000 people. It follows [v2 (preview)](https://huggingface.co/datasets/naiss-se/swedish-personas-v2), which held the structured layer and a 987-person pilot, and an external quality review of [v1](https://huggingface.co/datasets/birgermoell/swedish-personas).

**What is new since v2:** the text and work profile for all 100,000 people; names that follow where a person lives (first names by kommun for Swedish-heritage people, surnames by landsdel); a catalogue extended from 197 to 428 occupation groups; a sampled health-care contact per person.

Code: [github.com/BirgerMoell/swedish-personas](https://github.com/BirgerMoell/swedish-personas)

## At a glance

| Config | Rows | What it is |
|---|---|---|
| `personas_100k` (default) | 100,000 | Name, structured fields, Big Five scores, conditions, 11 text fields, work profile (null for the 49,015 who do not work) |
| `task_catalogue` | 4,348 | Work tasks per occupation group (428 groups), with a computer-based flag |
| `conditions_100k` | 143,786 | Health conditions per persona, with source and code |

All configs join on `uuid`.

```python
from datasets import load_dataset

repo = "naiss-se/swedish-personas-v3"
people = load_dataset(repo, "personas_100k", split="train")
p = people[0]
print(p["first_name"], p["last_name"], p["age"], p["kommun"])
print(p["persona"])

workers = people.filter(lambda r: r["job_title"] is not None)
for task in workers[0]["work_tasks"]:
    print(task["share_percent"], task["computer_based"], task["task"])

tasks = load_dataset(repo, "task_catalogue", split="train")
desk = tasks.filter(lambda t: t["computer_based"] == "helt")   # done entirely at a computer
```

## How it was made

Numbers come from statistics, words come from a model.

1. **Structured layer (no model).** Age, sex, county, municipality, country of birth, background, household, education, occupation, industry and employment are sampled from Statistics Sweden (SCB) tables, with several conditional tables combined so that, for example, occupation depends on education and age. Health conditions are drawn from Socialstyrelsen and Folkhälsomyndigheten prevalence by age and sex with a shared latent factor so related conditions co-occur. Big Five scores are drawn per person (mean 50, sd 10).
2. **Names.** Given names depend on sex, birth year and name heritage. For Swedish-heritage people they are also tilted by kommun, using SCB's newborn names per kommun 2020-2022 (empirical-Bayes shrinkage toward the county and the country; the effect fades to nothing for people born in 1965 or earlier). Swedish surnames are tilted by landsdel (Götaland, Svealand, Norrland) using SCB's table of the 25 surnames that differ most between regions; look-alike names follow at half strength. National name frequencies are unchanged. See `src/name_kommun.py` and `src/surname_tilt.py`.
3. **Work layer.** For each of 428 occupation groups the model turned the official description, job titles and skills from Arbetsförmedlingen's [JobTech Taxonomy](https://taxonomy.api.jobtechdev.se/) into 8-12 tasks (`task`, `computer_based` as `helt`/`delvis`/`nej`, `tools`, `output`). Each working person got a job title, workplace, seniority, tools and 4-7 task ids with a share of the week and a one-sentence detail. Ids are checked against the catalogue.
4. **Text.** Gemma 4 31B writes 11 text fields from the facts above. Rules forbid changing any fact, ban stock phrases, give each field a randomly drawn opening style, a sample of age-appropriate leisure ideas and a sampled health-care contact. A script checks and retries replies.

Model: `google/gemma-4-31B-it` on vLLM, two H200 GPUs per shard, four shards, on the Berzelius cluster (NSC, Linköping); temperature 0.9, schema-constrained JSON.

**How the names were applied.** The text was written with the names of the earlier (v2) structured layer. The v3 names were then swapped into the finished text by `src/name_swap.py`: first and last name replaced per person in every text field and in the work profile, only for people whose name changed (58,285 of 100,000). Sex, age and heritage did not change, so only the name tokens differ. 300 personas were regenerated from scratch with their v3 names: 17 whose first attempt failed and 283 flagged by the swap check (for example a text that reused a word from the old surname).

## Metrics (100,000 personas)

| Measure | v1 | v3 |
|---|---|---|
| Distinct given names / surnames | 40 / 40 | 3,734 / 13,040 |
| Distinct full names | 1,600 | 82,127 |
| Ten commonest surnames' share | 25.5% | 15.4% |
| Occupation vs education (Cramér's V) | 0.10 | 0.37 |
| Nurses with compulsory school only | 14.8% | 0% |
| Distinct occupations | 36 | 428 |
| County vs occupation (Cramér's V) | 0.028 | 0.119 |
| Diabetes with high blood pressure, adjusted lift | 0.99 | 1.45 |
| Anxiety with depression, adjusted lift | 0.99 | 5.32 |
| Five-word overlap between two personas (`persona`) | 14.3% | 0.04% |
| Share of the commonest opening, `persona` | - | 1.6% |
| Share of the commonest opening, `cultural_background` | - | 23.8% |

Weighted by time shares in the work profiles, 25% of working time goes to tasks done entirely at a computer (`helt`) and 33% to partly (`delvis`). Full metric files are in `reports/`.

## Fields

| Column | What it holds |
|---|---|
| `uuid` | Persona id, shared across configs |
| `first_name`, `last_name` | Sampled; Swedish-heritage names follow kommun (first) and landsdel (surname) |
| `sex`, `age` | From SCB's joint distribution; `sex` is registered binary sex, `age=100` means 100 or older |
| `marital_status`, `household_type`, `education_level` | SCB categories; household type is rule-based |
| `occupation`, `occupation_code`, `industry`, `employment_status` | SSYK 2012 four-digit group, industry, status |
| `country_of_birth`, `background`, `parents_country_of_birth` | Birthplace and SCB's background groups |
| `kommun`, `lan`, `country` | Municipality, county, `Sverige` |
| `name_heritage` | Name group: SV, FI, WEU, EEU, BALK, TR, AR, IR, HOA, SAS, EAS, LAT, AFR |
| `birth_year`, Big Five columns | 2025 minus age; T-scores 20-80 |
| `conditions` | List of sampled health conditions |
| `persona`, `cultural_background`, `professional_persona`, `skills_and_expertise`, `hobbies_and_interests`, `career_goals_and_ambitions`, `sports_persona`, `arts_persona`, `travel_persona`, `culinary_persona`, `healthcare_persona` | Model-written Swedish text |
| `skills_and_expertise_list`, `hobbies_and_interests_list` | Lists of 3-6 short items |
| `job_title`, `workplace`, `seniority`, `work_tools`, `work_tasks` | Work profile; `work_tasks` is a list of `{task_id, share_percent, task, computer_based, detail}` summing to 100 |

`task_catalogue`: `occupation_code`, `occupation`, `task_id`, `task`, `computer_based`, `tools`, `output`. `conditions_100k`: `uuid`, `source`, `code`, `condition`.

## Known limits

Read these before relying on the data.

**Names**
- **Local names are only approximate.** First-name factors apply only to Swedish-heritage given names and only for people born after 1965 (full strength from 2005). Surnames are tilted in three regions, not by kommun, because SCB publishes no surname table per kommun. The look-alike half-strength rule is an assumption.
- **The foreign-born mix is still per county, not per kommun**, so a place like Södertälje does not get its real share of people with Syriac or Iraqi background.
- **Name heritage labels are model-made;** a spot check found about 5% wrong. Names are drawn by broad region, not country.
- Spelling variants are not merged (Lukas and Lucas are treated as different names).

**Text and work layer**
- **Names were swapped into finished text** (see above). 64 texts have a new first name that also occurs as an ordinary word, and a few more reuse a word from the old surname; these were not all regenerated.
- **Repetition.** 23.8% of `cultural_background` texts open with "[Name] växte upp i", and "vårdcentral" appears in 16.7% of `healthcare_persona` texts (it was 51% before a targeted rewrite with a wider mix of care routes), still the most common single setting. "Fika" appears in 18%. Many texts say a parent grew up somewhere ("Lisas pappa växte upp i ...") as a way of describing family origin.
- **No native-speaker review of the full set.** Occasional misspellings occur.
- **Tasks, tools and time shares are plausible, not measured.** The catalogue is grounded in official occupation text, but no one has checked it, and some named software may not exist.
- **Details the structured layer does not fix are the model's choice**, including a partner's gender, children, pets and past jobs for pensioners; no year of arrival is in the data.

**Structured layer**
- The country-to-heritage mapping, comorbidity strengths and the name tilt strength are judgement calls, marked `ASSUMPTION` in the code.
- No modelling of national minorities (Sami, Tornedalians, Roma, Jews, Sweden Finns beyond the FI name group). Household type is rule-based. SCB's cells have disclosure-control noise.

**Use**

Use for Swedish-language prototyping, test fixtures, persona-conditioned generation and research on synthetic data. Do not use for demographic inference, allocation of public services, or decisions about individuals. The health fields are not for clinical or epidemiological inference. All personas are fictional; a persona can by coincidence share a name and town with a real person.

## Sources and licence

- **Statistics Sweden (SCB)**: population, name (including newborn names per kommun, and surnames per landsdel), background, education and occupation tables, fetched from open sources.
- **Socialstyrelsen** and **Folkhälsomyndigheten**: health rates.
- **Arbetsförmedlingen, JobTech Taxonomy**: occupation descriptions, job titles and skills for the task catalogue.
- **Gemma 4 31B** (Google): text and task catalogue.
- **Nemotron-Personas** (NVIDIA) and **Nemotron-Personas-Belgium** (Pleias): schema and generation recipe.

Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with attribution to the sources above. Code: MIT.

## Citation

```bibtex
@misc{moell2026swedishpersonasv3,
  title  = {Swedish Personas v3: 100,000 synthetic Swedish personas with SCB-conditioned structure, local names, model-written text and work tasks},
  author = {Moell, Birger},
  year   = {2026},
  publisher = {NAISS},
  url    = {https://huggingface.co/datasets/naiss-se/swedish-personas-v3}
}
```
