import csv, os, time, threading
import networkx as nx
from routing.backup import build_topology, backup_path

class ForwardingManager:
    def __init__(self, graph=None, flows=(("h1", "h2"),),
                 log_path="logs/swap_log.csv", install=None):
        self.graph = graph or build_topology()
        self.flows = list(flows)
        self.install = install or (lambda flow, path: None) 
        self.log_path = log_path
        self.lock = threading.Lock()
        self.active = {f: nx.shortest_path(self.graph, *f) for f in self.flows}
        self.standby = {}   
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        if not os.path.exists(log_path):
            with open(log_path, "w", newline="") as fh:
                csv.writer(fh).writerow(["ts", "link", "event", "flow", "swap_ms", "result"])

    @staticmethod
    def _edge(link):
        a, b = link.split("-")
        return (a, b)

    def _uses(self, path, edge):
        pairs = set(zip(path, path[1:]))
        return edge in pairs or edge[::-1] in pairs

    def _log(self, ts, link, event, flow, ms, result):
        with open(self.log_path, "a", newline="") as fh:
            csv.writer(fh).writerow([ts, link, event, flow, f"{ms:.3f}", result])

    def on_at_risk(self, link, ts):
        edge = self._edge(link)
        with self.lock:
            for flow in self.flows:
                if self._uses(self.active[flow], edge):
                    t0 = time.perf_counter()
                    p = backup_path(self.graph, *flow, edge)
                    ms = (time.perf_counter() - t0) * 1000
                    if p:
                        self.standby[(link, flow)] = p
                    self._log(ts, link, "backup_computed", flow, ms,
                              "stored" if p else "no_backup")

    def _swap(self, link, ts, event):
        edge = self._edge(link)
        with self.lock:
            for flow in self.flows:
                if not self._uses(self.active[flow], edge):
                    continue
                t0 = time.perf_counter()
                p = self.standby.get((link, flow))
                if not p:
                    result = "fallback_ospf_rip"
                else:
                    try:
                        if self.install(flow, p) is False:
                            raise RuntimeError("install returned False")
                    except Exception as exc:
                        result = f"install_failed:{type(exc).__name__}"
                    else:
                        self.active[flow] = p
                        result = "swapped"
                self._log(ts, link, event, flow,
                        (time.perf_counter() - t0) * 1000, result)

    def on_hard_cutoff(self, link, ts):
        self._swap(link, ts, "hard_cutoff")

    def on_link_failure(self, link, ts):
        self._swap(link, ts, "link_failure")

    def on_clear(self, link, ts):
        with self.lock:
            for key in [k for k in self.standby if k[0] == link]:
                del self.standby[key]
            self._log(ts, link, "clear", "-", 0.0, "standby_dropped")