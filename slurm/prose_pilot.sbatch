#!/usr/bin/env bash
#SBATCH -J personas-prose
#SBATCH --gpus=2
#SBATCH -c 28
#SBATCH --mem=300G
#SBATCH -t 01:00:00
# Prose pilot: Gemma 4 31B writes the task catalogue, work profiles and text fields.
# Submit with the account, partition and log file on the command line, and set:
#   WORK   folder holding prose_generate.py, the seeds file and ssyk4.json (outputs are written here)
#   IMAGE  vLLM container (.sif), MODEL  path to google/gemma-4-31B-it
#   PYPATH optional extra PYTHONPATH inside the container (for a newer transformers)
# Example: WORK=... IMAGE=... MODEL=... sbatch -A <account> -p <partition> -o <log> slurm/prose_pilot.sbatch
set -euo pipefail
: "${WORK:?}" "${IMAGE:?}" "${MODEL:?}"
SEEDS=${SEEDS:-seeds_1000_v2.jsonl}
OUT=${OUT:-pilot2_1000.jsonl}
PORT=$((20000 + SLURM_JOB_ID % 20000))
APPTAINERENV_PYTHONPATH=${PYPATH:-} apptainer exec --nv -B "$WORK" -B "$MODEL" "$IMAGE" vllm serve "$MODEL" \
  --port $PORT --served-model-name gemma-4-31b --tensor-parallel-size 2 --max-model-len 8192 --gpu-memory-utilization 0.90 > "$WORK/vllm-$SLURM_JOB_ID.log" 2>&1 &
pid=$!
trap 'kill $pid 2>/dev/null || true' EXIT
for i in $(seq 1 180); do
  curl -fsS http://127.0.0.1:$PORT/v1/models >/dev/null 2>&1 && break
  kill -0 $pid 2>/dev/null || { echo "vllm died" >&2; tail -60 "$WORK/vllm-$SLURM_JOB_ID.log" >&2; exit 1; }
  sleep 5
done
apptainer exec -B "$WORK" "$IMAGE" python3 "$WORK/prose_generate.py" "$WORK/$SEEDS" "$WORK/$OUT" \
  --taxonomy "$WORK/ssyk4.json" --catalogue "$WORK/task_catalogue.jsonl" --url http://127.0.0.1:$PORT/v1 --workers 48
