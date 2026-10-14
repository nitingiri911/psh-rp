#!/usr/bin/env bash
# Repeat the failover test for every baseline.
# Usage:  sudo bash run_baseline.sh <runs> [blackhole|down] [link]
#   sudo bash run_baseline.sh 1                    # sanity check, about 9 minutes
#   sudo bash run_baseline.sh 30                   # final data, about 4.5 hours
#   sudo bash run_baseline.sh 30 blackhole r1-r2   # same, explicit
RUNS=${1:-3}
MODE=${2:-blackhole}
LINK=${3:-r1-r2}
cd "$(dirname "$0")"
# proto timers post-seconds pre-jitter-seconds
for cfg in "ospf default 60 10" "ospf tuned 15 2" "rip default 260 30" "rip tuned 40 5"; do
  set -- $cfg
  proto=$1; timers=$2; post=$3; jitter=$4
  [ "$MODE" = "down" ] && post=15
  for i in $(seq 1 "$RUNS"); do
    mn -c >/dev/null 2>&1
    python3 failover_test.py --proto "$proto" --timers "$timers" --mode "$MODE" --link "$LINK" \
        --post "$post" --pre-jitter "$jitter" --run "$i" 2>&1 | grep -E "RESULT|Error|Traceback|aborted"
  done
done
echo "Done. Results: ../logs/baseline_failover.csv"
