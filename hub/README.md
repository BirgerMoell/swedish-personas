---
language:
- sv
license: cc-by-4.0
tags:
- synthetic
- personas
- swedish
- demographics
configs:
- config_name: default
  data_files:
  - split: train
    path: data/swedish_personas_100k.parquet
---

# Swedish Personas

100,000 fictional Swedish persona descriptions and structured attributes. The core demographic distribution is sampled from 2025 aggregate statistics from Statistics Sweden (SCB). The records are synthetic and do not come from individual people.

## Creation

The [generation code and GitHub Pages site](https://github.com/BirgerMoell/swedish-personas) document the complete process. The generator samples SCB's joint county × age × registered sex × marital-status population cells, then samples municipalities by county population totals. It creates other fields and Swedish descriptions with a fixed-seed, rule-based generator. **No LLM was used.**

## Fields

`uuid`, `professional_persona`, `healthcare_persona`, `sports_persona`, `arts_persona`, `travel_persona`, `culinary_persona`, `persona`, `cultural_background`, `skills_and_expertise`, `skills_and_expertise_list`, `hobbies_and_interests`, `hobbies_and_interests_list`, `career_goals_and_ambitions`, `sex`, `age`, `marital_status`, `household_type`, `education_level`, `occupation`, `kommun`, `lan`, `country`.

The columns follow [Nemotron-Personas](https://docs.nvidia.com/nemo/datadesigner/dev-notes/designing-nemotron-personas) (as in Nemotron-Personas-France), with `kommun` (municipality) and `lan` (county) as the Swedish locale fields. As in Nemotron, names and personality scores are not columns, but each persona text names the person. The `*_list` columns are stringified lists. `sex` is SCB's registered binary sex, not gender identity; texts use han/hon accordingly. Ages of 100 and above are `age=100`. `occupation` is `not_in_workforce` for children, students, pensioners and others without an assigned job. `household_type`, `education_level`, `occupation` and all prose are rule-based and **not** calibrated to SCB.

## Health information

`healthcare_persona` (a column in Nemotron's Data Designer persona set, omitted from the public France release) describes health conditions and patient behaviour in one sentence. Conditions are drawn from two open Swedish sources, fetched by `python3 src/fetch_health.py` (see `data/health_source.json`):

- **Socialstyrelsen**, [statistics database, diagnoses in inpatient and/or specialised outpatient care](https://sdb.socialstyrelsen.se/if_dia_sluten_oppen/), 2024: patients per 100,000 by 5-year age band and sex for 44 ICD-10 codes (heart disease, stroke, COPD, cancers, osteoarthritis, dementia, ADHD, autism, Crohn's, psoriasis and others). This measures people seen in specialist care in a year, **not** total prevalence; conditions managed in primary care are under-counted.
- **Folkhälsomyndigheten**, [National Public Health Survey](https://fohm-app.folkhalsomyndigheten.se/Folkhalsodata/pxweb/sv/A_Folkhalsodata/A_Folkhalsodata__B_HLV/), 2024: self-reported shares by age band (16-29, 30-44, 45-64, 65-84, 85+) and sex for people aged 16+ (allergy, asthma, diabetes, high blood pressure, eczema, headache, incontinence, back and musculoskeletal pain, obesity, severe anxiety, doctor-diagnosed depression, severe sleep problems). Under-16s use the Socialstyrelsen rates only.

Each persona's conditions are independent draws from the rate for its age and sex, so there is no comorbidity structure (for example, diabetes does not raise the chance of high blood pressure), and 16-17-year-olds use the 16-29 survey band. The companion file `data/swedish_personas_100k_conditions.parquet` lists the sampled conditions (`uuid`, `source`, `code`, `condition`) and is not part of the Nemotron schema. `validate.py` checks that observed condition counts match the source rates for every condition expected at least 200 times. This is synthetic data for prototyping and language work, not for clinical or epidemiological inference.

## Intended uses and limits

Use for Swedish-language prototyping, software test fixtures and research on synthetic text. Do not use for demographic inference, allocation of public services, or decisions about individuals. The source's 2025 cells have disclosure-control noise and the synthetic sample has sampling error. Municipality is drawn conditionally on county only. Country of birth, education, work, interests and text are illustrative heuristics, **not population calibrated**. The prose is template generated and has narrower linguistic variety than a high-quality model-generated corpus. Synthetic descriptions may coincidentally resemble real people.

## Source and license

Source: [Statistics Sweden, Population by region, marital status, age and sex, 2025](https://www.statistikdatabasen.scb.se/pxweb/en/ssd/START__BE__BE0101__BE0101A/BefolkningCKM/), table 000007ME. Health rates: Socialstyrelsen (statistics database, diagnoses in inpatient and specialised outpatient care, 2024) and Folkhälsomyndigheten (National Public Health Survey, 2024); please cite them as sources. Attribution required under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The dataset's code is separately MIT licensed in the GitHub repository.
