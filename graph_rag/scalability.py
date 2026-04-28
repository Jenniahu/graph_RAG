"""Scalability testing: measure algorithm runtime vs. graph scale and partitions."""

import csv
import json
import os
import random

from .config import Config
from .algorithms.pagerank import time_pagerank_spark, time_pagerank_with_partitions
from .algorithms.community import time_louvain_networkx


def sample_subgraph(fraction, seed=42,
                    vertices_path="output_jsonl/vertices.jsonl",
                    edges_path="output_jsonl/edges.jsonl"):
    """Sample a subgraph by fraction.

    Args:
        fraction: Fraction of vertices to sample (0.0 - 1.0).
        seed: Random seed.
        vertices_path: Path to vertices JSONL.
        edges_path: Path to edges JSONL.

    Returns:
        (sampled_vertices list, sampled_edges list)
    """
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


def run_scaling_experiments(cfg=None):
    """Run PageRank and Louvain at different graph scales.

    Args:
        cfg: Config instance. Uses defaults if None.

    Returns:
        List of result dicts.
    """
    if cfg is None:
        cfg = Config()

    os.makedirs(cfg.output_dir, exist_ok=True)
    results = []

    for fraction in cfg.scalability_fractions:
        label = f"{fraction:.0%}"
        print(f"\n=== Scale: {label} ===")
        vertices, edges = sample_subgraph(
            fraction, seed=cfg.scalability_seed,
            vertices_path=cfg.vertices_path, edges_path=cfg.edges_path,
        )

        pr_time = time_pagerank_spark(vertices, edges, cfg=cfg, max_iter=cfg.max_iter)
        louvain_time = time_louvain_networkx(edges, seed=cfg.louvain_seed)

        results.append({
            "fraction": fraction,
            "label": label,
            "num_vertices": len(vertices),
            "num_edges": len(edges),
            "pagerank_sec": round(pr_time, 2),
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

    Args:
        cfg: Config instance. Uses defaults if None.

    Returns:
        List of result dicts.
    """
    if cfg is None:
        cfg = Config()

    print("\n=== Partition Strategy Experiment (full graph) ===")
    vertices, edges = sample_subgraph(
        1.0, seed=cfg.scalability_seed,
        vertices_path=cfg.vertices_path, edges_path=cfg.edges_path,
    )
    partition_results = []

    for n_parts in cfg.partition_counts:
        label = f"{n_parts} partitions"
        t = time_pagerank_with_partitions(vertices, edges, num_partitions=n_parts, cfg=cfg, max_iter=cfg.max_iter)
        partition_results.append({
            "partitions": n_parts,
            "label": label,
            "pagerank_sec": round(t, 2),
        })

    with open(cfg.partition_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=partition_results[0].keys())
        writer.writeheader()
        writer.writerows(partition_results)

    print(f"Saved to {cfg.partition_csv}")
    return partition_results
