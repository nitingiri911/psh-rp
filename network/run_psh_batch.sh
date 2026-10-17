#!/usr/bin/env bash
# PSH-RP against plain OSPF under the same degradation, interleaved so slow drift hits all configs equally.
# Each round: gradual degradation (60 s ramp) and sudden failure (no ramp), on tuned and default OSPF timers.
# Usage:  sudo bash run_psh_batch.sh <rounds> [blackhole|down] [first-run-number]
#   sudo bash run_psh_batch.sh 10            # about 4 hours
ROUNDS=${1:-5}
MODE=${2:-blackhole}
START=${3:-1}
cd "$(dirname "$0")"
for i in $(seq "$START" $((START + ROUNDS - 1))); do
  for cfg in "tuned 30 60 --psh" "tuned 30 60" "default 60 60 --psh" "default 60 60" \
             "tuned 30 0 --psh" "tuned 30 0" "default 60 0 --psh" "default 60 0"; do
    set -- $cfg
    timers=$1; post=$2; ramp=$3; psh=${4:-}
    mn -c >/dev/null 2>&1
    python3 psh_failover_test.py --proto ospf --timers "$timers" --failure "$MODE" \
        --post "$post" --ramp "$ramp" --run "$i" $psh 2>&1 | grep -E "RESULT|Error|Traceback|aborted|SWAP FAILED"
  done
done
echo "Done. Results: ../logs/psh_failover.csv"
