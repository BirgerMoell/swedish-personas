#!/usr/bin/env bash
#SBATCH -J health-rewrite
#SBATCH --gpus=2
#SBATCH -c 28
#SBATCH --mem=300G
#SBATCH -t 03:00:00
# Rewrites only healthcare_persona for all 100,000 personas (see src/health_rewrite.py). One array task per shard,
# each with its own vLLM server on 2 GPUs. Resumable: submit again and finished personas are skipped.
#   WORK   folder with health_rewrite.py, prose_generate.py and health_input.jsonl
#   IMAGE  vLLM container (.sif), MODEL  path to google/gemma-4-31B-it, PYPATH optional, SHARDS (default 4)
set -euo pipefail
: "${WORK:?}" "${IMAGE:?}" "${MODEL:?}"
SHARDS=${SHARDS:-4}
TASK=${SLURM_ARRAY_TASK_ID:-0}
PORT=$((20000 + SLURM_JOB_ID % 20000))
APPTAINERENV_PYTHONPATH=${PYPATH:-} apptainer exec --nv -B "$WORK" -B "$MODEL" "$IMAGE" vllm serve "$MODEL" \
  --port $PORT --served-model-name gemma-4-31b --tensor-parallel-size 2 --max-model-len 8192 --gpu-memory-utilization 0.90 > "$WORK/vllm-health-$SLURM_JOB_ID.log" 2>&1 &
pid=$!
trap 'kill $pid 2>/dev/null || true' EXIT
for i in $(seq 1 180); do
  curl -fsS http://127.0.0.1:$PORT/v1/models >/dev/null 2>&1 && break
  kill -0 $pid 2>/dev/null || { echo "vllm died" >&2; tail -60 "$WORK/vllm-health-$SLURM_JOB_ID.log" >&2; exit 1; }
  sleep 5
done
apptainer exec -B "$WORK" "$IMAGE" python3 "$WORK/health_rewrite.py" run "$WORK/health_input.jsonl" "$WORK/health_shard${TASK}of${SHARDS}.jsonl" \
  --url http://127.0.0.1:$PORT/v1 --workers 64 --shard $TASK/$SHARDS
