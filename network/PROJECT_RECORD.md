# PSH-RP project record

Predictive Self-Healing Hybrid Routing Protocol. Course: Computer Networks (BCSE308P).
This file explains the whole project, and in detail the part done by Yashashwi Jain (Member 1, network and baselines).

| Member | Registration no. | Role |
|---|---|---|
| Yashashwi Jain | 24BCE2112 | Member 1: network, baselines, failover measurement, demo |
| Nitin | 24BCE2132 | Member 2: prediction engine (telemetry, scoring, detection) |
| Arsh Parvez | 24BCE2151 | Member 3: backup paths, forwarding table manager, scalability |

## 1. Summary

OSPF and RIP react only after a link has failed, so packets are lost while the failure is detected and routes are recomputed. PSH-RP is an overlay that runs on top of an unmodified OSPF or RIP. It probes every link, scores its health, flags links that are degrading, computes a backup path in advance, and installs it before the link dies.

Main results (emulated, one topology, silent failure):

- When a link degrades before failing, PSH-RP installs the backup about 30 s before the failure and the failure causes **no outage in any of 30 runs**. Packets lost over the run drop by 73% against OSPF with tuned timers and 93% against OSPF with default timers.
- When the failure is sudden, PSH-RP is **comparable to tuned OSPF** (2.35 s against 2.29 s) and far better than default OSPF (2.5 s against 31.7 s). The help there comes from fast detection by probing, not from prediction.
- Probes add load: the engine sends 5 pings per link per second, about 980 bytes/s per link.

## 2. Scope and honest limits

PSH-RP targets failures that degrade first (congestion, flaky links, wireless). A cable cut gives no warning, and then PSH-RP only detects the failure quickly. Limits: one emulated topology, one flow, one failed link, synthetic linear degradation, one failure type (blackhole) in the failover results, 10 runs per failover configuration, two machines with different Ubuntu and FRR versions, no BFD baseline, packet counts depend on the ping sender's rate in WSL2.

## 3. Repository layout and ownership

| Folder | Owner | Content |
|---|---|---|
| `network/` | Yashashwi | topology, impairment tools, baselines, failover test, demo, capture scripts |
| `engine/`, `tests/`, `tools/` | Nitin | telemetry, scoring, detector, engine, live runner, batch and summary tools |
| `routing/`, `sim/`, `eval/` | Arsh | backup path calculator, forwarding table manager, scalability simulation |
| `docs/interfaces.md` | shared | contract between modules |
| `results/` | shared | final CSV results |
| `logs/` | not in git | raw run logs |

Rules used: one branch per member (`feat/network` for Yashashwi), no commits to `main`, work reaches `main` through a pull request merged by a teammate, `git push --force-with-lease` only after a rebase.

## 4. Architecture

```
Telemetry collector -> Health scoring engine -> Backup path calculator -> Forwarding table manager
 (probe each link)      (score, adaptive          (shortest path that       (store standby route,
                         threshold, at-risk)       avoids the risky link)    install on cutoff or failure)
```

OSPF or RIP (FRRouting) keeps routing as normal underneath. Callbacks `on_at_risk`, `on_hard_cutoff` and `on_clear` (each `(link, ts)`) connect the engine to the forwarding table manager. All timestamps are `time.time()` epoch seconds on one machine.

## 5. Test network (built by Yashashwi)

- Six routers `r1..r6` and two hosts `h1`, `h2` in Mininet. Each router runs FRRouting zebra plus ospfd or ripd.
- Links: `r1-r2`, `r2-r6` (primary path), `r1-r3`, `r3-r4`, `r4-r6` (alternate), `r2-r5` (noisy link), `r5-r4`. Each has 2 ms delay.
- Primary path `h1-r1-r2-r6-h2`. Backup path `r1-r3-r4-r6`.
- Naming contract used by all modules: interface `<self>-<peer>` (for example `r2-r6`), link subnets `10.0.<i>.0/30` by link index (first node .1, second .2), host LANs `192.168.1.0/24` (h1 .10) and `192.168.2.0/24` (h2 .10).
- Timers: OSPF default hello 10 s and dead 40 s, tuned hello 1 s and dead 3 s. RIP default update 30 s and timeout 180 s, tuned 5 s and 15 s.
- Impairments with Linux `tc netem`: delay, jitter and loss, applied in both directions.

## 6. Algorithm (built by Nitin, summarised)

- Health score from latency, jitter and loss (loss weighted highest) plus a trend term over a sliding window.
- Per-link adaptive threshold: mean minus 2 standard deviations of the link's own history. Warm-up of 30 samples uses a fixed threshold of 85. History is frozen while a link is at-risk.
- At-risk after 3 consecutive samples below the threshold. Hard cutoff when health falls below 40. Clear after 5 consecutive samples above the threshold.
- The probe interval is 1 s. The engine runs four variants side by side on the same data: `psh` (full), `fixed`, `no_trend`, `no_hard`.

## 7. Yashashwi's work in detail

### 7.1 Environment
- Set up Ubuntu 24.04.1 under WSL2 (Python 3.12.3), Mininet, FRRouting 8.4.4, iperf3, tcpdump, tshark and the Python packages. `network/setup.sh` automates it and checks that `tc netem` works.
- Found and fixed that FRR refuses to run as root unless root is in the `frrvty` group (`sudo usermod -aG frrvty root`, added to `setup.sh`). Nitin hit the same error on Ubuntu 26.04.
- Ubuntu 24.04 blocks `pip install`, so the packages come from apt.

### 7.2 Topology and routing configuration: `psh_topo.py`
- `build_net`, `set_ips`, `write_configs`, `start_frr`, `stop_frr`, `wait_converged`, plus the constants `LINKS` and `NOISY_LINK`. Nitin's tools import these names, so they must not be renamed.
- Generates a zebra and ospfd or ripd config per router, starts the daemons inside each Mininet node, and waits until h1 can reach h2.
- Options: `--proto ospf|rip`, `--timers default|tuned`, `--noisy`, `--check`.
- Bugs found and fixed: Mininet overwrote each node's first interface IP with `10.0.0.x` (fixed by setting every IP explicitly in `set_ips`), the hosts had no default route, and FRR start errors were hidden (now shown).

### 7.3 Impairment tools: `netem_ctl.py`
`degrade`, `restore`, `cut` (interface down), `blackhole` (100% loss, link stays up, found only by routing timers), `heal`, `make_noisy`, and `ramp` (delay up to 200 ms, jitter up to 40 ms and loss up to 20% over N seconds). Each returns timestamps so logs can be matched.

### 7.4 Link table: `links.py`
`link_table(net)` returns `{"r1-r2": (node, "r1-r2", "10.0.1.2"), ...}` for the engine's probes.

### 7.5 Baseline failover measurement: `failover_test.py`, `ping_analysis.py`, `run_baseline.sh`
- Method: converge, run `ping -D` from h1 to h2 at a 10 ms interval, fail a link after a random delay, then compute **outage** (failure to the first real reply after the gap) and **packets lost** (missing sequence numbers).
- Two failure modes: `blackhole` (silent, default) and `down`.
- `run_baseline.sh <runs> [mode] [link]` repeats this for OSPF and RIP, default and tuned.
- Bug found and fixed: the first parser counted ICMP "Unreachable" lines as replies, which made default-timer outages look like 13 to 15 s instead of about 35 s. Only lines with "bytes from" count now.
- Other fixes: random 0 to N s delay before the failure (so it lands at a random point of the hello cycle), RIP default observation window raised from 220 to 260 s, raw ping output saved to `logs/raw/`.
- Result, 30 runs each, silent failure of r1-r2 (mean ± 95% CI): OSPF default 35.84 ± 1.08 s, OSPF tuned 2.56 ± 0.19 s, RIP default 194.5 ± 4.9 s, RIP tuned 15.36 ± 0.82 s. Each falls inside the range its own timers predict.

### 7.6 Overhead: `capture_overhead.py`
tcpdump on one link for 120 s with protocol filters. Results (bytes/s): OSPF default 20.1, OSPF tuned 169.1, RIP default 9.7, RIP tuned 58.4, one ICMP probe per second 192.7. Nitin pointed out that the engine really sends 5 pings per link per second, about 980 bytes/s, about 5.8 times tuned OSPF, so the single-probe row is only the minimum. The script now has a `--engine-only` capture with the real engine running.

### 7.7 PSH-RP failover test with a real route swap: `route_install.py`, `psh_failover_test.py`, `run_psh_batch.sh`
- `route_install.py` installs backup routes with `ip route replace ... metric 1` on every router of the path (forward and return), through `nsenter`, and checks the result with `ip route get`. Errors are returned, rolled back and logged.
- `psh_failover_test.py` runs one test: healthy period, a 60 s ramp (or none for a sudden failure), a silent failure, and more traffic. `--psh` runs Nitin's engine with the swap logic. `--manager fib` uses Arsh's `ForwardingManager` instead of the built-in logic. The failure time is randomised and engine logs go to the repo's `logs/`.
- `run_psh_batch.sh` interleaves PSH-RP and plain OSPF, tuned and default, gradual and sudden, so slow drift hits all configurations equally.
- Results, 10 runs each, mean ± 95% CI:

| Scenario | Configuration | Outage (s) | Packets lost | Backup swapped |
|---|---|---|---|---|
| Gradual | Plain OSPF default | 28.73 ± 3.99 | 2664 ± 250 | none |
| Gradual | Plain OSPF tuned | 1.68 ± 0.89 | 797 ± 119 | none |
| Gradual | PSH-RP default | 0.00 ± 0.00 | 188 ± 29 | 30.2 s before |
| Gradual | PSH-RP tuned | 0.00 ± 0.00 | 216 ± 36 | 28.1 s before |
| Sudden | Plain OSPF default | 31.74 ± 2.31 | 2091 ± 145 | none |
| Sudden | Plain OSPF tuned | 2.29 ± 0.54 | 153 ± 16 | none |
| Sudden | PSH-RP default | 2.51 ± 0.21 | 155 ± 13 | 2.5 s after |
| Sudden | PSH-RP tuned | 2.35 ± 0.19 | 146 ± 11 | 2.4 s after |

- Integration run with Arsh's manager (10 runs, gradual, tuned): outage 0.00 ± 0.00 s, swap 30.5 ± 4.2 s before the failure, 211 ± 61 packets lost. Two runs swapped about 20 s before the failure and lost 349 and 388 packets.

### 7.8 Live demo: `demo.py`
One command, about 4 minutes: `sudo python3 network/demo.py`. It runs the same degrading link first with plain OSPF, then with PSH-RP (using Arsh's manager by default), prints a line per second, and ends with a comparison table. The monitor counts loss from gaps in the ping sequence numbers, so a slow ping sender is not shown as loss. During a total outage the line says NO REPLIES. The numbers it prints are one short run, not statistics.

### 7.9 Cross-checks and process
- Reproduced Nitin's engine scenarios on a second laptop and found they agree, with one difference that Nitin later resolved with more runs.
- Found that Nitin's runs used an interface-down failure while the baselines used a blackhole, so lead times and baseline convergence could not be compared. Nitin added a `--failure` option and reran with the blackhole.
- Moved results into `results/` for the team, opened pull requests, resolved diverged branches with rebase and `--force-with-lease`, and wrote the team's git workflow into practice.
- Documents: Review 1, Review 2 and a conference-style paper (IEEE format, 5 pages), all updated as the numbers were corrected.
- The code and documents were developed with help from an AI assistant. Every command was run and every number measured by the team on their own machines. Follow your course's rules on disclosing this.

## 8. Other results (Nitin, 30 runs each, silent failure)

Warning before the failure: S1 (60 s ramp) psh 55.2 ± 1.5 s, fixed 48.3 ± 0.4 s. S2 (15 s ramp) psh 12.5 ± 0.1 s, fixed 10.3 ± 0.2 s. Hard-cutoff warning: S1 31.6 ± 1.5 s with the trend term and 23.5 s without it, S2 5.6 ± 0.5 s and 2.7 s. The trend term does not change the first flag. S3 (sudden): the full design detects the failure 2.32 ± 0.10 s after it, the fixed threshold 4.81 ± 0.26 s, no hard cutoff 4.44 ± 0.21 s.

False alarms per run on a healthy noisy link: default noise psh 0.10 ± 0.11, fixed 0.27 ± 0.19 (not significant). High noise (jitter 30 ms, loss 3%): psh 0.13 ± 0.13, fixed 1.97 ± 0.40. About 1.2 warm-up alarms per run occur at high noise.

Sensitivity (descriptive, tuned and evaluated on the same logs): at a false-alarm rate like fixed thresholds of 70 to 75, the adaptive threshold gives about 12 to 15 s more warning. A sigma multiplier of 3 gives much less warning. A trend weight of 4 looks better than the 2 used. A hard cutoff of 20 fires at the cut and is useless. The baseline freeze matters only for slow decays, which were tested only in simulation.

Arsh: backup path calculator (networkx, at-risk link removed, 3-hop neighbourhood search), forwarding table manager (standby per link and flow, swap on hard cutoff, swap log), unit tests, and a scalability simulation at 10, 25 and 50 nodes. His scalability numbers are not in `main` yet.

## 9. How to reproduce

```bash
bash network/setup.sh                                              # once
sudo python3 network/psh_topo.py --proto ospf --timers tuned --check
sudo bash network/run_baseline.sh 30 blackhole r1-r2               # baselines, hours
sudo python3 network/psh_failover_test.py --proto ospf --timers tuned --psh --manager fib --run 1
sudo bash network/run_psh_batch.sh 10 blackhole                    # about 4 hours
sudo python3 network/capture_overhead.py --engine-only             # overhead with the real engine
sudo python3 network/demo.py                                       # live demo
```

Run one Mininet job at a time. Each run starts with `mn -c`, which kills any other running job.

## 10. Bugs and corrections, in short

FRR group error, pip blocked on Ubuntu 24.04, wrong interface IPs from Mininet, missing host default routes, hidden FRR errors, ping parser counting ICMP errors, failure timing always at the same phase, RIP window too short, root-owned log files, engine logs written to the wrong folder, route install ignoring errors, overhead measured with one ping instead of the engine, demo monitor mistaking a slow sender for loss, tcpdump parser matching a header line, failure types differing between baselines and engine runs, and several wrong or old numbers that Nitin corrected.

## 11. Still open

- **Yashashwi:** record the demo video, run the engine overhead capture, run the interface-down batch (optional), check names and registration numbers.
- **Nitin:** reproduce the failover result on his machine, merge pending pull requests, supply any remaining sensitivity numbers.
- **Arsh:** merge the scalability results into `results/scalability.csv`, compare the 3-hop search against unlimited search at 10, 25 and 50 nodes (same path, how often it returns None), push the swap-log fix and tests, and answer how a failed install is signalled.
- **Team:** one agreed set of final numbers, who presents which part, and which laptop runs the demo. The paper has three placeholders for Arsh's scalability times.

## 12. Glossary

- **Blackhole:** the link stays up but drops everything, so only routing timers can find it.
- **Outage:** time from the failure to the first reply after the gap in replies.
- **Warning (lead time):** seconds between the first at-risk flag and the failure.
- **Hard cutoff:** health below 40, when the standby route is installed.
- **Standby route:** the precomputed backup path, stored but not yet active.
- **CI:** 95% confidence interval from Student's t.
