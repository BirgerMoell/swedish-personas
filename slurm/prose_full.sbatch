#!/usr/bin/env bash
#SBATCH -J personas-full
#SBATCH --gpus=2
#SBATCH -c 28
#SBATCH --mem=300G
#SBATCH -t 12:00:00
# Full run: Gemma 4 31B writes the work profile and text fields for all 100,000 personas.
# One array task per shard, each with its own vLLM server on 2 GPUs. Resumable: submit again and
# finished personas are skipped, failed ones are retried.
# Needs the task catalogue to be complete first (run once with MODE=catalogue and no --array).
#   WORK   folder with prose_generate.py, seeds_100k.jsonl, ssyk4.json, task_catalogue.jsonl
#   IMAGE  vLLM container (.sif), MODEL  path to google/gemma-4-31B-it, PYPATH optional
#   SHARDS number of shards (default 4); MODE=catalogue writes only the catalogue
#   SEEDS  seeds file in WORK (default seeds_100k.jsonl), OUTNAME output file name (default per shard)
set -euo pipefail
: "${WORK:?}" "${IMAGE:?}" "${MODEL:?}"
SHARDS=${SHARDS:-4}
SEEDS=${SEEDS:-seeds_100k.jsonl}
TASK=${SLURM_ARRAY_TASK_ID:-0}
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
if [ "${MODE:-}" = "catalogue" ]; then
  EXTRA="--catalogue-only"; OUT=catalogue_only.jsonl
else
  EXTRA="--shard $TASK/$SHARDS"; OUT=${OUTNAME:-personas_shard${TASK}of${SHARDS}.jsonl}
fi
apptainer exec -B "$WORK" "$IMAGE" python3 "$WORK/prose_generate.py" "$WORK/$SEEDS" "$WORK/$OUT" \
  --taxonomy "$WORK/ssyk4.json" --catalogue "$WORK/task_catalogue.jsonl" --url http://127.0.0.1:$PORT/v1 --workers 64 $EXTRA
