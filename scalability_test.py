import json
import random
import time
import csv
import os
import sys

# Ensure Spark workers use the same Python as the driver
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


def sample_subgraph(fraction, seed=42,
                    vertices_path="output_jsonl/vertices.jsonl",
                    edges_path="output_jsonl/edges.jsonl"):
    """Sample a subgraph by fraction. Returns (sampled_vertices list, sampled_edges list)."""
    random.seed(seed)
    all_vertices = []
    with open(vertices_path) as f:
        for line in f:
            all_vertices.append(json.loads(line))

    n = int(len(all_vertices) * fraction)
    sampled = random.sample(all_vertices, n)
    sampled_ids = {v["id"] for v in sampled}

    sampled_edges = []
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            if e["src"] in sampled_ids and e["dst"] in sampled_ids:
                sampled_edges.append(e)

    print(f"[Sample {fraction:.0%}] vertices={len(sampled)}, edges={len(sampled_edges)}")
    return sampled, sampled_edges


def time_pagerank_spark(vertices, edges, max_iter=10):
    """Run PageRank via Spark GraphFrames and return elapsed seconds."""
    from pyspark.sql import SparkSession
    from graphframes import GraphFrame

    spark = (SparkSession.builder
             .appName("ScalabilityTest")
             .config("spark.jars.packages",
                     "graphframes:graphframes:0.8.3-spark3.5-s_2.12")
             .config("spark.sql.shuffle.partitions", "100")
             .getOrCreate())
    spark.sparkContext.setCheckpointDir("/tmp/sc_checkpoints")

    v_df = spark.createDataFrame(vertices)
    e_df = spark.createDataFrame(edges)
    g = GraphFrame(v_df, e_df)

    t0 = time.time()
    results = g.pageRank(resetProbability=0.15, maxIter=max_iter)
    results.vertices.count()  # trigger action to materialize
    elapsed = time.time() - t0

    spark.stop()
    print(f"  PageRank time={elapsed:.1f}s")
    return elapsed


def time_louvain_networkx(edges, seed=42):
    """Run Louvain on NetworkX and return elapsed seconds."""
    import networkx as nx

    G = nx.Graph()
    for e in edges:
        G.add_edge(e["src"], e["dst"])

    t0 = time.time()
    communities = nx.community.louvain_communities(G, seed=seed)
    elapsed = time.time() - t0

    print(f"  Louvain communities={len(communities)}, time={elapsed:.1f}s")
    return elapsed


def run_experiments():
    os.makedirs("output_jsonl", exist_ok=True)
    results = []

    for fraction, label in [(0.25, "25%"), (0.5, "50%"), (1.0, "100%")]:
        print(f"\n=== Scale: {label} ===")
        vertices, edges = sample_subgraph(fraction)

        pr_time = time_pagerank_spark(vertices, edges, max_iter=10)
        louvain_time = time_louvain_networkx(edges)

        results.append({
            "fraction": fraction,
            "label": label,
            "num_vertices": len(vertices),
            "num_edges": len(edges),
            "pagerank_sec": round(pr_time, 2),
            "louvain_sec": round(louvain_time, 2),
        })

    with open("output_jsonl/scalability_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print("\nSaved to output_jsonl/scalability_results.csv")
    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['label']:>5}: vertices={r['num_vertices']:>7}, edges={r['num_edges']:>6}, "
              f"PageRank={r['pagerank_sec']:>6.1f}s, Louvain={r['louvain_sec']:>5.1f}s")
    return results


def time_pagerank_with_partitions(vertices, edges, num_partitions, max_iter=10):
    """Run PageRank with a specific number of Spark partitions and return elapsed seconds."""
    from pyspark.sql import SparkSession
    from graphframes import GraphFrame

    spark = (SparkSession.builder
             .appName(f"PartitionTest-{num_partitions}")
             .config("spark.jars.packages",
                     "graphframes:graphframes:0.8.3-spark3.5-s_2.12")
             .config("spark.sql.shuffle.partitions", str(num_partitions))
             .getOrCreate())
    spark.sparkContext.setCheckpointDir("/tmp/sc_checkpoints")

    v_df = spark.createDataFrame(vertices).repartition(num_partitions)
    e_df = spark.createDataFrame(edges).repartition(num_partitions)
    g = GraphFrame(v_df, e_df)

    t0 = time.time()
    results = g.pageRank(resetProbability=0.15, maxIter=max_iter)
    results.vertices.count()
    elapsed = time.time() - t0

    spark.stop()
    print(f"  {num_partitions} partitions: PageRank time={elapsed:.1f}s")
    return elapsed


def run_partition_experiments():
    """Run PageRank with different partition strategies on the full graph."""
    print("\n=== Partition Strategy Experiment (full graph) ===")
    vertices, edges = sample_subgraph(1.0)
    partition_results = []

    for n_parts, label in [(50, "50 partitions"), (100, "100 partitions"), (200, "200 partitions")]:
        t = time_pagerank_with_partitions(vertices, edges, num_partitions=n_parts)
        partition_results.append({
            "partitions": n_parts,
            "label": label,
            "pagerank_sec": round(t, 2),
        })

    with open("output_jsonl/partition_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=partition_results[0].keys())
        writer.writeheader()
        writer.writerows(partition_results)

    print("Saved to output_jsonl/partition_results.csv")
    return partition_results


if __name__ == "__main__":
    run_experiments()
    run_partition_experiments()
