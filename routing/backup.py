import networkx as nx

def build_topology():
    g = nx.Graph()
    edges = [("h1","r1"),("r1","r2"),("r2","r6"),("r6","h2"),
             ("r1","r3"),("r3","r4"),("r4","r6"),("r2","r5"),("r5","r4")]
    for u, v in edges:
        g.add_edge(u, v, weight=1)
    return g

def backup_path(graph, src, dst, bad_link, hops=3):
    """Shortest src->dst path avoiding bad_link, limited to a k-hop
    neighbourhood around the link. Returns a node list or None."""
    u, v = bad_link
    g = graph.copy()
    if g.has_edge(u, v):
        g.remove_edge(u, v)
    near = {src, dst}
    for n in (u, v):
        near |= set(nx.single_source_shortest_path_length(graph, n, cutoff=hops))
    try:
        return nx.shortest_path(g.subgraph(near), src, dst, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None