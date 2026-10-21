# PSH-RP: Predictive Self-Healing Routing as an Overlay on OSPF and RIP

Course project, Computer Networks (BCSE308P), VIT Vellore.
Yashashwi Jain (24BCE2112), Nitin (24BCE2132), Arsh Parvez (24BCE2151).

PSH-RP probes every link for latency, jitter and loss, scores link health, flags a degrading link
with a per-link adaptive threshold, precomputes a backup path and installs it before the link fails.
It runs on top of an unmodified OSPF or RIP (FRRouting) in an emulated Mininet network.

## Layout

| Folder | Contents | Owner |
| --- | --- | --- |
| `engine/` | telemetry probes, health score (level and trend), adaptive detector, engine, config | Nitin |
| `routing/` | backup path calculator and forwarding table manager, with tests | Arsh |
| `network/` | Mininet and FRR topology, netem tools, baselines, failover tests, demo, overhead capture | Yashashwi |
| `sim/` | scalability simulations (`scale.py`, `scale_extra.py`) | Arsh, Nitin |
| `tools/` | scenario runner, 30-run batch runner, replay and parameter sweeps, summaries | Nitin |
| `tests/` | unit tests for scoring and detection | Nitin |
| `results/` | summary CSVs and graphs (raw logs stay in `logs/`, which git ignores) | all |
| `docs/interfaces.md` | data formats between the modules | all |

## Requirements

Ubuntu (tested on 24.04 with FRR 8.4.4 and 26.04 with FRR 10.5.1) on WSL2 or a Linux VM,
root access, Mininet 2.3.0, FRRouting, Open vSwitch, `tc netem`, Python 3 with `networkx`
(`matplotlib` and `pandas` for graphs).

## Setup

```bash
cd network && bash setup.sh && cd ..
sudo service openvswitch-switch start
```

On newer Ubuntu, if the FRR daemons exit with "not part of vty group frrvty", run
`sudo usermod -aG frrvty root` and start again.

## Quick checks (run everything from the repository root)

```bash
python3 -m pytest -q
sudo python3 network/psh_topo.py --proto ospf --timers tuned --check
```

## Experiments

```bash
# Prediction on a degrading link: s1 (60 s ramp), s2 (15 s ramp), s3 (sudden), s4 (noisy link, no failure)
sudo python3 -m tools.run_live --scenario s1 --failure blackhole

# 30 runs with mean, standard deviation and 95% confidence interval (do not press Ctrl+C while it runs)
sudo python3 -m tools.batch --scenario s1 --runs 30 --failure blackhole --prefix s1_bh

# Parameter sweeps replayed from the saved logs: noise prefix first, ramp prefix second
python3 -m tools.replay s4_hi s1_bh

# Failover with a real route swap, then plain OSPF under the same degradation
sudo python3 network/psh_failover_test.py --proto ospf --timers tuned --psh --manager fib --run 1
sudo python3 network/psh_failover_test.py --proto ospf --timers tuned --run 1

# Baselines (30 runs), control-traffic overhead, scalability
sudo bash network/run_baseline.sh 30 blackhole r1-r2
sudo python3 network/capture_overhead.py --secs 120
python3 -m sim.scale_extra

# Live demo: plain OSPF, then PSH-RP, same degradation and failure (about 4 minutes)
sudo python3 network/demo.py
```

Each batch run is marked finished by `logs/<tag>_done`. An interrupted run is repeated when the
batch is started again. Summaries are written to `results/`.

## Main results

Mean with 95% confidence interval, silent (blackhole) failure.

- Warning before the failure (30 runs): 55.2 s (S1) and 12.5 s (S2) with the adaptive threshold,
  against 48.3 s and 10.3 s with a fixed threshold of 85.
- Noisy healthy link, false alarms per run (30 runs): 0.13 adaptive against 1.97 fixed at high noise.
  At default noise the difference is not significant.
- Failover (10 runs each): after a gradual degradation PSH-RP has no outage, against 1.68 s (OSPF tuned)
  and 28.7 s (OSPF default). After a sudden failure it matches tuned OSPF (2.35 s against 2.29 s)
  and is far faster than default OSPF (2.5 s against 31.7 s).

## Limits

One emulated topology, one flow, one failed link, one failure type for the failover results,
10 runs per failover configuration, results from two machines with different Ubuntu and FRR versions,
and parameters tuned and evaluated on the same logs. See the paper for the full list.
