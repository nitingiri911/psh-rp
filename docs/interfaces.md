links: built from network/psh_topo.py LINKS, link i = (a, b) becomes "a-b": (net[a], "a-b", "10.0.i.2"), probed from a toward b
probe sample: {"latency": ms, "jitter": ms, "loss": percent}
Engine(links, probe_fn, on_at_risk=f(link, ts), on_hard_cutoff=f(link, ts), on_clear=f(link, ts), tag="run")
ts: time.time() epoch seconds, one VM only
callbacks run in the link's probe thread and must return fast
logs/<tag>_telemetry.csv: ts,link,latency,jitter,loss,variant,health,threshold,at_risk
logs/<tag>_events.csv: ts,link,variant,event (at_risk, hard_cutoff, clear)
logs/<tag>_failures.csv: ts,link,event (ramp_start, cut), written by tools/run_live.py from netem_ctl.ramp
variants: psh (primary, drives callbacks), fixed, no_trend, no_hard
Arsh provides: routing/callbacks.py with on_at_risk(link, ts), on_hard_cutoff(link, ts), on_clear(link, ts), and a swap-time log
Yashie provides: topology and netem_ctl.py. Others only read them. Do not rename their functions without telling Nitin.
