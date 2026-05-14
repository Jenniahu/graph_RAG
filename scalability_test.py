"""Entry point for scalability and partition experiments.

Usage:
    python scalability_test.py --data-version v5                    # full run
    python scalability_test.py --data-version v5 --fraction 0.25   # single scale (PR only)
    python scalability_test.py --data-version v5 --louvain-only    # louvain-only CSV merge
    python scalability_test.py --data-version v5 --partition-only  # partition only
"""

import argparse
import csv
import json
import os
import time

from graph_rag import Config
from graph_rag.scalability import sample_subgraph


def run_pagerank_for_fraction(fraction, cfg):
    """Run PageRank for one fraction in the current process. Returns elapsed seconds."""
    from pyspark.sql import SparkSession
    from graphframes import GraphFrame

    vertices, edges = sample_subgraph(
        fraction, seed=cfg.scalability_seed,
        vertices_path=cfg.vertices_path, edges_path=cfg.edges_path,
        entity_edge_sources=cfg.entity_edge_sources,
    )
    print(f"[Sample {fraction:.0%}] vertices={len(vertices)}, edges={len(edges)}")

    spark = (SparkSession.builder
             .appName(f"ScalabilityTest-{fraction:.0%}")
             .config("spark.jars.packages", cfg.graphframes_package)
             .config("spark.sql.shuffle.partitions", "100")
             .getOrCreate())
    spark.sparkContext.setCheckpointDir(cfg.checkpoint_dir)

    v_df = spark.createDataFrame(vertices)
    e_df = spark.createDataFrame(edges)
    g = GraphFrame(v_df, e_df)
    t0 = time.time()
    res = g.pageRank(resetProbability=cfg.reset_prob, maxIter=cfg.max_iter)
    res.vertices.count()
    elapsed = round(time.time() - t0, 2)
    print(f"  PageRank time={elapsed:.1f}s")
    spark.stop()
    return len(vertices), len(edges), elapsed


def run_louvain_for_fraction(fraction, cfg):
    """Run Louvain for one fraction. Returns elapsed seconds."""
    from graph_rag.algorithms.community import time_louvain_networkit

    vertices, edges = sample_subgraph(
        fraction, seed=cfg.scalability_seed,
        vertices_path=cfg.vertices_path, edges_path=cfg.edges_path,
        entity_edge_sources=cfg.entity_edge_sources,
    )
    return time_louvain_networkit(edges, seed=cfg.louvain_seed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG Scalability Experiments")
    parser.add_argument("--data-version", choices=["v4", "v5", "input"], default="v5")
    parser.add_argument("--fraction", type=float, default=None,
                        help="Run PageRank for one fraction (no Louvain)")
    parser.add_argument("--louvain-only", action="store_true",
                        help="Run Louvain only for all fractions, then merge CSV")
    parser.add_argument("--partition-only", action="store_true",
                        help="Run partition experiments only")
    args = parser.parse_args()

    cfg = Config(data_version=args.data_version)
    os.makedirs(cfg.output_dir, exist_ok=True)

    if args.fraction is not None:
        # Single fraction PageRank mode (called by wrapper scripts per-fraction)
        fraction = args.fraction
        nv, ne, pr_time = run_pagerank_for_fraction(fraction, cfg)
        # Write or append to CSV
        row = {
            "fraction": fraction,
            "label": f"{fraction:.0%}",
            "num_vertices": nv,
            "num_edges": ne,
            "pagerank_sec": pr_time,
            "louvain_sec": -1,  # placeholder, filled by --louvain-only
        }
        write_header = not os.path.exists(cfg.scalability_csv)
        with open(cfg.scalability_csv, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        print(f"Saved to {cfg.scalability_csv}: {row}")

    elif args.louvain_only:
        # Run Louvain for all fractions, update CSV louvain_sec column
        rows = []
        if os.path.exists(cfg.scalability_csv):
            with open(cfg.scalability_csv) as f:
                rows = list(csv.DictReader(f))

        louvain_results = {}
        for frac in cfg.scalability_fractions:
            lt = run_louvain_for_fraction(frac, cfg)
            louvain_results[frac] = round(lt, 2)
            print(f"  {frac:.0%} Louvain time={lt:.1f}s")

        # Merge into existing rows
        merged = []
        for row in rows:
            frac = float(row["fraction"])
            row["louvain_sec"] = louvain_results.get(frac, row["louvain_sec"])
            merged.append(row)

        if not merged:
            # No existing CSV, create new
            merged = [
                {"fraction": f, "label": f"{f:.0%}",
                 "num_vertices": -1, "num_edges": -1,
                 "pagerank_sec": -1, "louvain_sec": louvain_results[f]}
                for f in cfg.scalability_fractions
            ]

        with open(cfg.scalability_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=merged[0].keys())
            writer.writeheader()
            writer.writerows(merged)
        print(f"Updated {cfg.scalability_csv}")

    elif args.partition_only:
        from graph_rag.scalability import run_partition_experiments
        run_partition_experiments(cfg)

    else:
        # Full run: call this script 3 times as subprocesses (once per fraction),
        # then run Louvain in one shot, then run partition experiments.
        import subprocess
        import sys

        script = __file__
        dv = args.data_version

        # Step 1: PageRank per fraction (each in its own JVM)
        os.remove(cfg.scalability_csv) if os.path.exists(cfg.scalability_csv) else None
        for frac in cfg.scalability_fractions:
            print(f"\n>>> Running PageRank {frac:.0%} as subprocess...")
            result = subprocess.run(
                [sys.executable, script, "--data-version", dv, "--fraction", str(frac)],
                capture_output=False, text=True
            )
            if result.returncode not in (0, 139):
                print(f"  WARNING: fraction {frac} exited with code {result.returncode}")

        # Step 2: Louvain for all fractions (no Spark, safe in one process)
        print("\n>>> Running Louvain for all fractions...")
        subprocess.run(
            [sys.executable, script, "--data-version", dv, "--louvain-only"],
            capture_output=False, text=True
        )

        # Step 3: Partition experiments
        print("\n>>> Running partition experiments...")
        subprocess.run(
            [sys.executable, script, "--data-version", dv, "--partition-only"],
            capture_output=False, text=True
        )

        print("\n=== All scalability experiments done ===")
        if os.path.exists(cfg.scalability_csv):
            with open(cfg.scalability_csv) as f:
                for row in csv.DictReader(f):
                    print(f"  {row['label']:>5}: vertices={row['num_vertices']}, "
                          f"edges={row['num_edges']}, "
                          f"PageRank={row['pagerank_sec']}s, Louvain={row['louvain_sec']}s")
