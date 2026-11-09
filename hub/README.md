---
pretty_name: Swedish Personas
language:
- sv
license: cc-by-4.0
task_categories:
- text-generation
size_categories:
- 10K<n<100K
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
- synthetic-data
- scb
configs:
- config_name: default
  data_files:
  - split: train
    path: data/swedish_personas_100k.parquet
---

<p align="center">
  <img src="images/banner.png" alt="Swedish Personas: a dot map of Sweden where every coloured dot is one synthetic persona" width="100%">
</p>

<h1 align="center">Swedish Personas</h1>

<p align="center"><b>Sverige, en person i taget.</b><br>100,000 fictional Swedish personas in the Nemotron-Personas format.</p>

<p align="center">
[![License: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-8a6bff?style=flat-square)](https://creativecommons.org/licenses/by/4.0/)
[![Personas](https://img.shields.io/badge/personas-100%2C000-3df5d0?style=flat-square)](https://huggingface.co/datasets/birgermoell/swedish-personas)
[![Format](https://img.shields.io/badge/format-Nemotron--Personas-ff5fb0?style=flat-square)](https://docs.nvidia.com/nemo/datadesigner/dev-notes/designing-nemotron-personas)
[![Language](https://img.shields.io/badge/language-Svenska-4aa8ff?style=flat-square)](https://huggingface.co/datasets/birgermoell/swedish-personas)
[![Website](https://img.shields.io/badge/website-live-ffb36c?style=flat-square)](https://birgermoell.github.io/swedish-personas/)
</p>

<p align="center"><a href="https://birgermoell.github.io/swedish-personas/">Website</a> · <a href="https://github.com/BirgerMoell/swedish-personas">GitHub</a> · <a href="https://docs.nvidia.com/nemo/datadesigner/dev-notes/designing-nemotron-personas">Nemotron-Personas</a></p>

---

## At a glance

| | |
|---|---|
| **Personas** | 100,000, fictional, in Swedish |
| **Format** | 23 columns, following [Nemotron-Personas](https://docs.nvidia.com/nemo/datadesigner/dev-notes/designing-nemotron-personas) |
| **Geography** | all 21 counties (`lan`) and 290 municipalities (`kommun`) |
| **Demographics** | sampled from SCB's 2025 joint distribution of county, age, sex and marital status |
| **Health** | `healthcare_persona` from Socialstyrelsen and Folkhälsomyndigheten age and sex rates |
| **Generation** | fixed-seed, rule-based, no LLM, fully reproducible |
| **License** | data CC BY 4.0, code MIT |

## A persona

```json
{
  "uuid": "140ed6c27dd90d271bf3ea34828073ff",
  "professional_persona": "Arvid Ekström arbetar som systemutvecklare inom it och telekom i Luleå med fokus på programmering och systemdesign.",
  "healthcare_persona": "Arvid Ekström lever med högt blodtryck och ringer 1177 för råd innan han kontaktar vården.",
  "persona": "Arvid Ekström är nyfiken och provar gärna nya saker och föredrar små sällskap framför stora fester, med fikakulturen och att ta paus tillsammans som en självklar del av vardagen och släktforskning som en fast punkt i veckan i Luleå.",
  "cultural_background": "Arvid växte upp i Norrbotten. I vardagen märks fikakulturen och att ta paus tillsammans, och det lokala livet i Norrbotten präglas av Jukkasjärvi och Kiruna.",
  "skills_and_expertise_list": "['programmering', 'systemdesign', 'versionshantering', 'kodgranskning']",
  "hobbies_and_interests_list": "['släktforskning', 'svampplockning', 'löpning', 'simning']",
  "career_goals_and_ambitions": "Arvid överväger att byta bransch inom några år.",
  "sex": "Man",
  "age": 38,
  "marital_status": "ogift",
  "household_type": "sambo med hemmavarande barn",
  "education_level": "gymnasieexamen",
  "occupation": "systemutvecklare",
  "kommun": "Luleå",
  "lan": "Norrbotten",
  "country": "Sverige"
}
```

## Quick start

```python
from datasets import load_dataset

ds = load_dataset("birgermoell/swedish-personas", split="train")
print(ds[0]["persona"])

# Sampled health conditions, keyed by uuid
conditions = load_dataset(
    "birgermoell/swedish-personas",
    data_files="data/swedish_personas_100k_conditions.parquet",
    split="train",
)
```

## Fields

| Column | What it holds |
|---|---|
| `uuid` | Unique persona id |
| `persona` | One-sentence portrait of temperament and outlook |
| `professional_persona` | Work life, skills and place of work |
| `healthcare_persona` | Health conditions and patient behaviour, sampled from Swedish statistics |
| `sports_persona`, `arts_persona`, `travel_persona`, `culinary_persona` | Facets of leisure, culture, travel and food, tied to age and county |
| `cultural_background` | Roots, region and everyday traditions |
| `skills_and_expertise` / `_list` | Skills as prose and as a stringified list |
| `hobbies_and_interests` / `_list` | Interests as prose and as a stringified list |
| `career_goals_and_ambitions` | Plans suited to the persona's life stage |
| `sex`, `age`, `marital_status` | From SCB's joint distribution (`sex` is registered binary sex) |
| `household_type`, `education_level`, `occupation` | Heuristic, age-consistent; `not_in_workforce` when no job |
| `kommun`, `lan`, `country` | Municipality and county (Swedish counterparts of commune/département) |

The columns follow Nemotron-Personas (as in Nemotron-Personas-France). Names and personality scores are not columns, but each persona text names the person. `age=100` means 100 or older. `sex` reflects SCB's registered binary sex, not gender identity.

## Creation

The [generation code and GitHub Pages site](https://github.com/BirgerMoell/swedish-personas) document the complete process. The generator samples SCB's joint county × age × registered sex × marital-status population cells, then samples municipalities by county population totals. It creates other fields and Swedish descriptions with a fixed-seed, rule-based generator. **No LLM was used.**

## Health information

`healthcare_persona` (a column in Nemotron's Data Designer persona set, omitted from the public France release) describes health conditions and patient behaviour in one sentence. Conditions are drawn from two open Swedish sources, fetched by `python3 src/fetch_health.py` (see `data/health_source.json`):

- **Socialstyrelsen**, [statistics database, diagnoses in inpatient and/or specialised outpatient care](https://sdb.socialstyrelsen.se/if_dia_sluten_oppen/), 2024: patients per 100,000 by 5-year age band and sex for 44 ICD-10 codes (heart disease, stroke, COPD, cancers, osteoarthritis, dementia, ADHD, autism, Crohn's, psoriasis and others). This measures people seen in specialist care in a year, **not** total prevalence; conditions managed in primary care are under-counted.
- **Folkhälsomyndigheten**, [National Public Health Survey](https://fohm-app.folkhalsomyndigheten.se/Folkhalsodata/pxweb/sv/A_Folkhalsodata/A_Folkhalsodata__B_HLV/), 2024: self-reported shares by age band (16-29, 30-44, 45-64, 65-84, 85+) and sex for people aged 16+ (allergy, asthma, diabetes, high blood pressure, eczema, headache, incontinence, back and musculoskeletal pain, obesity, severe anxiety, doctor-diagnosed depression, severe sleep problems). Under-16s use the Socialstyrelsen rates only.

Each persona's conditions are independent draws from the rate for its age and sex, so there is no comorbidity structure (for example, diabetes does not raise the chance of high blood pressure), and 16-17-year-olds use the 16-29 survey band. The companion file `data/swedish_personas_100k_conditions.parquet` lists the sampled conditions (`uuid`, `source`, `code`, `condition`) and is not part of the Nemotron schema. `validate.py` checks that observed condition counts match the source rates for every condition expected at least 200 times. This is synthetic data for prototyping and language work, not for clinical or epidemiological inference.

## Intended uses and limits

Use for Swedish-language prototyping, software test fixtures and research on synthetic text. Do not use for demographic inference, allocation of public services, or decisions about individuals. The source's 2025 cells have disclosure-control noise and the synthetic sample has sampling error. Municipality is drawn conditionally on county only. Country of birth, education, work, interests and text are illustrative heuristics, **not population calibrated**. The prose is template generated and has narrower linguistic variety than a high-quality model-generated corpus. Synthetic descriptions may coincidentally resemble real people.

## Source and license

Source: [Statistics Sweden, Population by region, marital status, age and sex, 2025](https://www.statistikdatabasen.scb.se/pxweb/en/ssd/START__BE__BE0101__BE0101A/BefolkningCKM/), table 000007ME. Health rates: Socialstyrelsen (statistics database, diagnoses in inpatient and specialised outpatient care, 2024) and Folkhälsomyndigheten (National Public Health Survey, 2024); please cite them as sources. Attribution required under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The dataset's code is separately MIT licensed in the GitHub repository.

## Citation

```bibtex
@misc{moell2026swedishpersonas,
  title  = {Swedish Personas: 100,000 synthetic Swedish personas in the Nemotron-Personas format},
  author = {Moell, Birger},
  year   = {2026},
  url    = {https://huggingface.co/datasets/birgermoell/swedish-personas}
}
```
