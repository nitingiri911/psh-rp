import csv
import os
import threading
import time
import traceback
from engine import config as c
from engine.scoring import LinkScorer
from engine.detector import LinkDetector


def fmt(x):
    return "" if x is None else f"{x:.2f}"


class Engine:
    def __init__(self, links, probe_fn, on_at_risk=None, on_hard_cutoff=None, on_clear=None, tag="run", variants=None):
        os.makedirs("logs", exist_ok=True)
        self.links = list(links)
        self.probe_fn = probe_fn
        self.callbacks = {"at_risk": on_at_risk, "hard_cutoff": on_hard_cutoff, "clear": on_clear}
        self.variants = variants or c.VARIANTS
        self.state = {
            l: {n: (LinkScorer(v["alpha"]), LinkDetector(v["adaptive"], v["hard"])) for n, v in self.variants.items()}
            for l in self.links
        }
        self.lock = threading.Lock()
        self.stop_ev = threading.Event()
        self.threads = []
        self.tf = open(f"logs/{tag}_telemetry.csv", "w", newline="")
        self.ef = open(f"logs/{tag}_events.csv", "w", newline="")
        self.tw = csv.writer(self.tf)
        self.ew = csv.writer(self.ef)
        self.tw.writerow(["ts", "link", "latency", "jitter", "loss", "variant", "health", "threshold", "at_risk"])
        self.ew.writerow(["ts", "link", "variant", "event"])

    def _loop(self, link):
        nxt = time.time()
        while not self.stop_ev.is_set():
            try:
                t = self.probe_fn(link)
                ts = time.time()
                rows = []
                events = []
                for name, (scorer, det) in self.state[link].items():
                    h = scorer.update(t["latency"], t["jitter"], t["loss"])
                    th, risk, evs = det.update(h)
                    rows.append([f"{ts:.3f}", link, fmt(t["latency"]), fmt(t["jitter"]), fmt(t["loss"]),
                                 name, fmt(h), fmt(th), int(risk)])
                    events.extend((name, e) for e in evs)
                with self.lock:
                    self.tw.writerows(rows)
                    self.tf.flush()
                    for name, e in events:
                        self.ew.writerow([f"{ts:.3f}", link, name, e])
                    self.ef.flush()
                for name, e in events:
                    cb = self.callbacks.get(e)
                    if name == c.PRIMARY and cb:
                        cb(link, ts)
            except Exception:
                traceback.print_exc()
            nxt += c.PROBE_INTERVAL
            self.stop_ev.wait(max(0.0, nxt - time.time()))

    def start(self):
        self.threads = [threading.Thread(target=self._loop, args=(l,), daemon=True) for l in self.links]
        for t in self.threads:
            t.start()

    def stop(self):
        self.stop_ev.set()
        for t in self.threads:
            t.join()
        self.tf.close()
        self.ef.close()
