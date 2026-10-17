from routing.backup import build_topology, backup_path

def test_avoids_bad_link():
    p = backup_path(build_topology(), "h1", "h2", ("r2", "r6"))
    assert p[0] == "h1" and p[-1] == "h2"
    assert ("r2", "r6") not in zip(p, p[1:])
    assert ("r6", "r2") not in zip(p, p[1:])

def test_no_alternative_returns_none():
    assert backup_path(build_topology(), "h1", "h2", ("h1", "r1")) is None