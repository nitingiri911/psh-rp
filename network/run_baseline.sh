#!/usr/bin/env bash
# Repeat the failover test for every baseline.
# Usage:  sudo bash run_baseline.sh <runs> [blackhole|down]
#   sudo bash run_baseline.sh 2          # quick trial
#   sudo bash run_baseline.sh 30         # final data (takes hours, run it overnight)
RUNS=${1:-3}
MODE=${2:-blackhole}
cd "$(dirname "$0")"
for cfg in "ospf default 60" "ospf tuned 15" "rip default 260" "rip tuned 40"; do
  set -- $cfg
  proto=$1; timers=$2; post=$3
  [ "$MODE" = "down" ] && post=15
  for i in $(seq 1 "$RUNS"); do
    mn -c >/dev/null 2>&1
    python3 failover_test.py --proto "$proto" --timers "$timers" --mode "$MODE" --post "$post" --run "$i" 2>&1 | grep -E "RESULT|Error|Traceback|aborted"
  done
done
echo "Done. Results: ../logs/baseline_failover.csv"
