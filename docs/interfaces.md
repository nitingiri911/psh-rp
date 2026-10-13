links: one entry per LINKS item (a, b) at index i, as "a-b": (net[a], "a-b", "10.0.i.2"), probed from a toward b
probe sample: {"latency": ms, "jitter": ms, "loss": percent}
Engine(links, probe_fn, on_at_risk=f(link, ts), on_hard_cutoff=f(link, ts), on_clear=f(link, ts), tag="run")
ts: time.time() epoch seconds, one VM only
callbacks run in the link's probe thread and must return fast
logs/<tag>_telemetry.csv: ts,link,latency,jitter,loss,variant,health,threshold,at_risk
logs/<tag>_events.csv: ts,link,variant,event (at_risk, hard_cutoff, clear)
variants: psh (primary, drives callbacks), fixed, no_trend, no_hard
Member 1 provides: interface name and far-end IP per link, and logs/<tag>_failures.csv with ts,link,cut
Member 3 provides: the three callback functions and a swap-time log
