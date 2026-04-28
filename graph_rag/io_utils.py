"""File I/O utilities for graph analytics."""

import glob
import json


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


def load_graph(spark, vertices_path="output_jsonl/vertices.jsonl",
               edges_path="output_jsonl/edges.jsonl"):
    """Load a GraphFrame from JSONL vertex/edge files.

    Args:
        spark: Active SparkSession.
        vertices_path: Path to vertices JSONL.
        edges_path: Path to edges JSONL.

    Returns:
        GraphFrame instance.
    """
    from graphframes import GraphFrame
    v = spark.read.json(vertices_path)
    e = spark.read.json(edges_path)
    return GraphFrame(v, e)


def read_jsonl(path):
    """Read a .jsonl file and return a list of dicts."""
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(rows, path):
    """Write a list of dicts to a .jsonl file."""
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
