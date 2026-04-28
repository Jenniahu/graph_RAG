"""Community detection algorithms (Louvain) and enriched vertex merging."""

import time


def run_louvain_networkx(edges_path="output_jsonl/edges.jsonl", seed=42):
    """Run Louvain community detection using NetworkX.

    Args:
        edges_path: Path to edges JSONL file.
        seed: Random seed for reproducibility.

    Returns:
        ({node_id: community_id}, elapsed_seconds)
    """
    import networkx as nx
    import json

    t0 = time.time()
    G = nx.Graph()
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            G.add_edge(e["src"], e["dst"])

    communities = nx.community.louvain_communities(G, seed=seed)
    elapsed = time.time() - t0
    print(f"[Louvain] communities={len(communities)}, time={elapsed:.1f}s")

    node_to_community = {}
    for cid, members in enumerate(communities):
        for node in members:
            node_to_community[node] = cid
    return node_to_community, elapsed


def merge_and_save_enriched(pagerank_path="output_jsonl/vertices_with_pagerank.jsonl",
                             community_map=None,
                             out_path="output_jsonl/vertices_enriched.jsonl"):
    """Merge pagerank results with community IDs and save to vertices_enriched.jsonl.

    Args:
        pagerank_path: Path to the merged pagerank JSONL file.
        community_map: Dict mapping node_id -> community_id.
        out_path: Output path for enriched vertices.

    Returns:
        Number of written rows.
    """
    import json

    written = 0
    with open(pagerank_path) as f_in, open(out_path, "w") as f_out:
        for line in f_in:
            row = json.loads(line)
            row["community_id"] = int(community_map.get(row["id"], -1))
            f_out.write(json.dumps(row) + "\n")
            written += 1
    print(f"Saved enriched vertices to {out_path} ({written} rows)")
    return written


def time_louvain_networkx(edges, seed=42):
    """Run Louvain on NetworkX from in-memory edge list and return elapsed seconds.

    This variant accepts edges as a list of dicts (for scalability testing).

    Args:
        edges: List of edge dicts with 'src' and 'dst' keys.
        seed: Random seed for reproducibility.

    Returns:
        Elapsed seconds.
    """
    import networkx as nx

    G = nx.Graph()
    for e in edges:
        G.add_edge(e["src"], e["dst"])

    t0 = time.time()
    communities = nx.community.louvain_communities(G, seed=seed)
    elapsed = time.time() - t0

    print(f"  Louvain communities={len(communities)}, time={elapsed:.1f}s")
    return elapsed
