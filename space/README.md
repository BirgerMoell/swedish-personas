---
title: Swedish Personas Viewer
emoji: 🇸🇪
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
license: cc-by-4.0
short_description: Browse 100,000 synthetic Swedish people
datasets:
- RenaissanceLabsEU/swedish-personas-v3
---

# Swedish Personas viewer

A viewer for [Swedish Personas v3](https://huggingface.co/datasets/RenaissanceLabsEU/swedish-personas-v3): 100,000 synthetic Swedish people with SCB-conditioned structure, model-written Swedish text and work profiles.

Search the stories, filter by place, age, occupation, name group and health condition, click a dot on the map, read the full record with its work tasks, or copy a link to one person.

The app loads `data/personas_100k.parquet` from the dataset into DuckDB when it starts; restart the Space to pick up a new dataset version. Code: [github.com/RenaissanceLabs-EU/swedish-personas](https://github.com/RenaissanceLabs-EU/swedish-personas) (`space/`).

All people are fictional. Not for decisions about individuals.
