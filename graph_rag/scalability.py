"""Scalability testing: measure algorithm runtime vs. graph scale and partitions."""

import csv
import json
import os
import random
import time

from .config import Config
from .algorithms.pagerank import time_pagerank_spark, time_pagerank_with_partitions
from .algorithms.community import time_louvain_networkit


def sample_subgraph(fraction, seed=42,
                    vertices_path="output_jsonl/vertices.jsonl",
                    edges_path="output_jsonl/edges.jsonl",
                    entity_edge_sources=("extracted", "seed")):
    """Sample a subgraph by fraction, filtering to entity-entity only.

    Args:
        fraction: Fraction of vertices to sample (0.0 - 1.0).
        seed: Random seed.
        vertices_path: Path to vertices JSONL.
        edges_path: Path to edges JSONL.
        entity_edge_sources: Tuple of edge source values to keep.

    Returns:
        (sampled_vertices list, sampled_edges list)
    """
    random.seed(seed)
    all_vertices = []
    with open(vertices_path) as f:
        for line in f:
            v = json.loads(line)
            if v.get("node_type") == "entity":
                all_vertices.append(v)

    n = int(len(all_vertices) * fraction)
    sampled = random.sample(all_vertices, n)
    sampled_ids = {v["id"] for v in sampled}

    sampled_edges = []
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            if e.get("source") not in entity_edge_sources:
                continue
            if e["src"] in sampled_ids and e["dst"] in sampled_ids:
                sampled_edges.append(e)

    print(f"[Sample {fraction:.0%}] vertices={len(sampled)}, edges={len(sampled_edges)}")
    return sampled, sampled_edges


def run_scaling_experiments(cfg=None):
    """Run PageRank and Louvain at different graph scales.

    Uses a single shared SparkSession across all scale experiments to
    avoid segfault caused by repeated start/stop in the same process.

    Args:
        cfg: Config instance. Uses defaults if None.

    Returns:
        List of result dicts.
    """
    if cfg is None:
        cfg = Config()

    from pyspark.sql import SparkSession
    from graphframes import GraphFrame

    os.makedirs(cfg.output_dir, exist_ok=True)
    results = []

    # Pre-collect all sampled subgraphs first (to avoid Spark interfering with file I/O)
    samples = []
    for fraction in cfg.scalability_fractions:
        vertices, edges = sample_subgraph(
            fraction, seed=cfg.scalability_seed,
            vertices_path=cfg.vertices_path, edges_path=cfg.edges_path,
            entity_edge_sources=cfg.entity_edge_sources,
        )
        samples.append((fraction, vertices, edges))

    # Start a single SparkSession for all benchmarks
    spark = (SparkSession.builder
             .appName("ScalabilityTest")
             .config("spark.jars.packages", cfg.graphframes_package)
             .config("spark.sql.shuffle.partitions", "100")
             .getOrCreate())
    spark.sparkContext.setCheckpointDir(cfg.checkpoint_dir)

    for fraction, vertices, edges in samples:
        label = f"{fraction:.0%}"
        print(f"\n=== Scale: {label} ===")

        v_df = spark.createDataFrame(vertices)
        e_df = spark.createDataFrame(edges)
        g = GraphFrame(v_df, e_df)

        t0 = time.time()
        res = g.pageRank(resetProbability=cfg.reset_prob, maxIter=cfg.max_iter)
        res.vertices.count()
        pr_time = round(time.time() - t0, 2)
        print(f"  PageRank time={pr_time:.1f}s")

        louvain_time = time_louvain_networkit(edges, seed=cfg.louvain_seed)

        results.append({
            "fraction": fraction,
            "label": label,
            "num_vertices": len(vertices),
            "num_edges": len(edges),
            "pagerank_sec": pr_time,
            "louvain_sec": round(louvain_time, 2),
        })

    with open(cfg.scalability_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"\nSaved to {cfg.scalability_csv}")
    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['label']:>5}: vertices={r['num_vertices']:>7}, edges={r['num_edges']:>6}, "
              f"PageRank={r['pagerank_sec']:>6.1f}s, Louvain={r['louvain_sec']:>5.1f}s")
    return results


def run_partition_experiments(cfg=None):
    """Run PageRank with different partition strategies on the full graph.

    Note: Uses getOrCreate() - partition config changes noted in results but
    SparkSession is shared across calls to avoid JVM segfault on restart.

    Args:
        cfg: Config instance. Uses defaults if None.

    Returns:
        List of result dicts.
    """
    from pyspark.sql import SparkSession
    from graphframes import GraphFrame

    if cfg is None:
        cfg = Config()

    print("\n=== Partition Strategy Experiment (full graph) ===")
    vertices, edges = sample_subgraph(
        1.0, seed=cfg.scalability_seed,
        vertices_path=cfg.vertices_path, edges_path=cfg.edges_path,
        entity_edge_sources=cfg.entity_edge_sources,
    )
    partition_results = []

    # Use getOrCreate - SparkSession is reused, partition counts vary the data repartition
    spark = (SparkSession.builder
             .appName("PartitionTest")
             .config("spark.jars.packages", cfg.graphframes_package)
             .config("spark.sql.shuffle.partitions", str(max(cfg.partition_counts)))
             .getOrCreate())
    spark.sparkContext.setCheckpointDir(cfg.checkpoint_dir)

    for n_parts in cfg.partition_counts:
        label = f"{n_parts} partitions"

        v_df = spark.createDataFrame(vertices).repartition(n_parts)
        e_df = spark.createDataFrame(edges).repartition(n_parts)
        spark.conf.set("spark.sql.shuffle.partitions", str(n_parts))
        g = GraphFrame(v_df, e_df)

        t0 = time.time()
        res = g.pageRank(resetProbability=cfg.reset_prob, maxIter=cfg.max_iter)
        res.vertices.count()
        elapsed = round(time.time() - t0, 2)
        print(f"  {n_parts} partitions: PageRank time={elapsed:.1f}s")

        partition_results.append({
            "partitions": n_parts,
            "label": label,
            "pagerank_sec": elapsed,
        })

    with open(cfg.partition_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=partition_results[0].keys())
        writer.writeheader()
        writer.writerows(partition_results)

    print(f"Saved to {cfg.partition_csv}")
    return partition_results
