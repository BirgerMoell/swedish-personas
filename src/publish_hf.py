"""Publish the verified release to the authenticated personal Hugging Face account."""

from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import HfApi
from validate import validate

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PARQUET = DATA / "swedish_personas_100k.parquet"
if not PARQUET.exists() or pq.read_metadata(PARQUET).num_rows != 100_000:
    raise SystemExit("Refusing to publish: generate and verify exactly 100,000 rows first.")
validate(PARQUET)

api = HfApi()
username = api.whoami()["name"]
repo_id = f"{username}/swedish-personas"
api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=True)
for local, remote in (
    (ROOT / "hub/README.md", "README.md"),
    (ROOT / "LICENSE-DATA", "LICENSE"),
    (PARQUET, "data/swedish_personas_100k.parquet"),
    (DATA / "generation_report.json", "sources/generation_report.json"),
    (DATA / "source.json", "sources/source.json"),
    (DATA / "scb_county_age_sex_marital_2025.csv", "sources/scb_county_age_sex_marital_2025.csv"),
    (DATA / "scb_municipality_2025.csv", "sources/scb_municipality_2025.csv"),
):
    api.upload_file(path_or_fileobj=str(local), path_in_repo=remote, repo_id=repo_id, repo_type="dataset")
print(f"Published https://huggingface.co/datasets/{repo_id}")
