import time
from routing.fib_manager import ForwardingManager

def test_swap_uses_standby(tmp_path):
    m = ForwardingManager(log_path=str(tmp_path / "s.csv"))
    m.on_at_risk("r2-r6", time.time())
    m.on_hard_cutoff("r2-r6", time.time())
    assert ("r2", "r6") not in zip(m.active[("h1","h2")], m.active[("h1","h2")][1:])

def test_fallback_without_standby(tmp_path):
    m = ForwardingManager(log_path=str(tmp_path / "s.csv"))
    before = list(m.active[("h1", "h2")])
    m.on_link_failure("r2-r6", time.time())
    assert m.active[("h1", "h2")] == before
    assert "fallback_ospf_rip" in (tmp_path / "s.csv").read_text()

def test_clear_drops_standby(tmp_path):
    m = ForwardingManager(log_path=str(tmp_path / "s.csv"))
    m.on_at_risk("r2-r6", time.time())
    m.on_clear("r2-r6", time.time())
    assert not m.standby
def test_failed_install_is_not_marked_swapped(tmp_path):
    def bad(flow, path):
        raise RuntimeError("boom")
    m = ForwardingManager(log_path=str(tmp_path / "s.csv"), install=bad)
    before = list(m.active[("h1", "h2")])
    m.on_at_risk("r2-r6", time.time())
    m.on_hard_cutoff("r2-r6", time.time())
    assert m.active[("h1", "h2")] == before
    assert "install_failed" in (tmp_path / "s.csv").read_text()