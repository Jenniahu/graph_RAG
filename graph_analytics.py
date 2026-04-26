import time
import glob


def create_spark():
    from pyspark.sql import SparkSession
    return (SparkSession.builder
            .appName("GraphRAG-Analytics")
            .config("spark.jars.packages",
                    "graphframes:graphframes:0.8.3-spark3.5-s_2.12")
            .config("spark.sql.shuffle.partitions", "200")
            .getOrCreate())


def load_graph(spark, vertices_path="output_jsonl/vertices.jsonl",
               edges_path="output_jsonl/edges.jsonl"):
    from graphframes import GraphFrame
    v = spark.read.json(vertices_path)
    e = spark.read.json(edges_path)
    return GraphFrame(v, e)


def run_pagerank(g, reset_prob=0.15, max_iter=10):
    """Returns vertices DataFrame with pagerank column added, and elapsed time."""
    t0 = time.time()
    results = g.pageRank(resetProbability=reset_prob, maxIter=max_iter)
    elapsed = time.time() - t0
    print(f"[PageRank] maxIter={max_iter}, time={elapsed:.1f}s")
    return results.vertices, elapsed


def save_pagerank(vertices_pr, out_dir="output_jsonl/vertices_with_pagerank"):
    vertices_pr.write.mode("overwrite").json(out_dir)
    print(f"Saved pagerank results to {out_dir}/")


def merge_spark_parts(part_dir, out_path):
    """Merge Spark JSON part files into a single .jsonl file."""
    parts = sorted(glob.glob(f"{part_dir}/part-*.json"))
    if not parts:
        parts = sorted(glob.glob(f"{part_dir}/*.json"))
    if not parts:
        raise FileNotFoundError(f"No JSON part files found in {part_dir}")
    written = 0
    with open(out_path, "w") as out:
        for p in parts:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        out.write(line + "\n")
                        written += 1
    print(f"Merged {len(parts)} part files -> {out_path} ({written} rows)")


def run_louvain_networkx(edges_path="output_jsonl/edges.jsonl", seed=42):
    """Run Louvain community detection using NetworkX. Returns ({node_id: community_id}, elapsed)."""
    import networkx as nx
    import json as _json

    t0 = time.time()
    G = nx.Graph()
    with open(edges_path) as f:
        for line in f:
            e = _json.loads(line)
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
    """Merge pagerank results with community IDs and save to vertices_enriched.jsonl."""
    import json as _json

    written = 0
    with open(pagerank_path) as f_in, open(out_path, "w") as f_out:
        for line in f_in:
            row = _json.loads(line)
            row["community_id"] = int(community_map.get(row["id"], -1))
            f_out.write(_json.dumps(row) + "\n")
            written += 1
    print(f"Saved enriched vertices to {out_path} ({written} rows)")


if __name__ == "__main__":
    import json

    spark = create_spark()
    spark.sparkContext.setCheckpointDir("/tmp/graphframes_checkpoints")

    g = load_graph(spark)

    # PageRank
    v_pr, pr_time = run_pagerank(g, max_iter=10)
    save_pagerank(v_pr)

    # Print Top 10
    print("\n=== Top 10 PageRank Nodes ===")
    v_pr.orderBy("pagerank", ascending=False).select("name", "pagerank").show(10, truncate=False)

    spark.stop()

    # Merge Spark partition files -> single jsonl
    PR_DIR = "output_jsonl/vertices_with_pagerank"
    if not glob.glob(PR_DIR + ".jsonl"):
        merge_spark_parts(PR_DIR, PR_DIR + ".jsonl")

    # Save Top 100
    rows = []
    with open(PR_DIR + ".jsonl") as f:
        for line in f:
            rows.append(json.loads(line))

    top100 = sorted(rows, key=lambda x: x["pagerank"], reverse=True)[:100]
    with open("output_jsonl/pagerank_top100.jsonl", "w") as out:
        for r in top100:
            out.write(json.dumps(r) + "\n")
    print(f"\nTop 1: {top100[0]['name']}  pagerank={top100[0]['pagerank']:.4f}")

    # Louvain (NetworkX, single-machine)
    community_map, louvain_time = run_louvain_networkx()
    merge_and_save_enriched(community_map=community_map)

    # Quality check: Top 10 by PageRank with community
    print("\n=== Top 10 PageRank Nodes (with community) ===")
    enriched_rows = []
    with open("output_jsonl/vertices_enriched.jsonl") as f:
        for line in f:
            enriched_rows.append(json.loads(line))
    top10 = sorted(enriched_rows, key=lambda x: x["pagerank"], reverse=True)[:10]
    for r in top10:
        print(f"  [community {r['community_id']}] {r['name']}: {r['pagerank']:.4f}")
