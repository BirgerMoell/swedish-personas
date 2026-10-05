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

`id`, `first_name`, `age`, `age_100_plus`, `scb_sex`, `marital_status`, `county_code`, `county`, `municipality_code`, `municipality`, `country_of_birth`, `education`, `employment_status`, `sector`, `occupation`, `interest_1`, `interest_2`, `value`, `goal`, `communication`, `persona_sv`.

The `scb_sex` field reflects the two categories in SCB's source table. It is not a gender-identity field. `age=100` with `age_100_plus=true` denotes age 100 or older.

## Intended uses and limits

Use for Swedish-language prototyping, software test fixtures and research on synthetic text. Do not use for demographic inference, allocation of public services, or decisions about individuals. The source's 2025 cells have disclosure-control noise and the synthetic sample has sampling error. Municipality is drawn conditionally on county only. Country of birth, education, work, interests and text are illustrative heuristics, **not population calibrated**. The prose is template generated and has narrower linguistic variety than a high-quality model-generated corpus. Synthetic descriptions may coincidentally resemble real people.

## Source and license

Source: [Statistics Sweden, Population by region, marital status, age and sex, 2025](https://www.statistikdatabasen.scb.se/pxweb/en/ssd/START__BE__BE0101__BE0101A/BefolkningCKM/), table 000007ME. Attribution required under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The dataset's code is separately MIT licensed in the GitHub repository.
