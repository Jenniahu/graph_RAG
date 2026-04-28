"""Tests for graph analytics pipeline.

Includes:
- Package import tests (verify refactored modules load correctly)
- Output schema and integrity tests (verify pipeline results)
"""

import json
import pathlib

# ============================================================
# Package import tests
# ============================================================

def test_import_config():
    from graph_rag.config import Config
    cfg = Config()
    assert cfg.max_iter == 10
    assert cfg.reset_prob == 0.15


def test_import_spark_utils():
    from graph_rag.spark_utils import create_spark
    assert callable(create_spark)


def test_import_io_utils():
    from graph_rag.io_utils import merge_spark_parts, load_graph, read_jsonl, write_jsonl
    assert callable(merge_spark_parts)
    assert callable(load_graph)
    assert callable(read_jsonl)
    assert callable(write_jsonl)


def test_import_pagerank():
    from graph_rag.algorithms.pagerank import run_pagerank, save_pagerank, extract_top_n
    assert callable(run_pagerank)
    assert callable(save_pagerank)
    assert callable(extract_top_n)


def test_import_community():
    from graph_rag.algorithms.community import run_louvain_networkx, merge_and_save_enriched
    assert callable(run_louvain_networkx)
    assert callable(merge_and_save_enriched)


def test_import_pipeline():
    from graph_rag.pipeline import Pipeline
    assert callable(Pipeline)


def test_import_scalability():
    from graph_rag.scalability import sample_subgraph, run_scaling_experiments, run_partition_experiments
    assert callable(sample_subgraph)
    assert callable(run_scaling_experiments)
    assert callable(run_partition_experiments)


def test_import_top_level():
    from graph_rag import Config, Pipeline
    assert callable(Pipeline)
    cfg = Config()
    assert cfg.vertices_path == "output_jsonl/vertices.jsonl"


# ============================================================
# Output data integrity tests (require pipeline has been run)
# ============================================================

DATA_DIR = pathlib.Path("output_jsonl")


def test_vertices_schema():
    with open(DATA_DIR / "vertices.jsonl") as f:
        row = json.loads(f.readline())
    assert "id" in row
    assert "name" in row
    assert "type" in row


def test_edges_schema():
    with open(DATA_DIR / "edges.jsonl") as f:
        row = json.loads(f.readline())
    assert "src" in row
    assert "dst" in row
    assert "relation" in row
    assert "source" in row


def test_no_dangling_edges():
    vertex_ids = set()
    with open(DATA_DIR / "vertices.jsonl") as f:
        for line in f:
            vertex_ids.add(json.loads(line)["id"])
    dangling = 0
    with open(DATA_DIR / "edges.jsonl") as f:
        for line in f:
            e = json.loads(line)
            if e["src"] not in vertex_ids or e["dst"] not in vertex_ids:
                dangling += 1
    assert dangling == 0, f"{dangling} dangling edges found"


def test_pagerank_output_exists():
    p = pathlib.Path("output_jsonl/vertices_with_pagerank.jsonl")
    assert p.exists(), "Run graph_analytics.py first"


def test_pagerank_output_schema():
    with open("output_jsonl/vertices_with_pagerank.jsonl") as f:
        row = json.loads(f.readline())
    assert "pagerank" in row, "Missing pagerank column"
    assert isinstance(row["pagerank"], float), "pagerank must be float"
    assert row["pagerank"] >= 0.0


def test_louvain_output_schema():
    with open("output_jsonl/vertices_enriched.jsonl") as f:
        row = json.loads(f.readline())
    assert "community_id" in row, "Missing community_id column"
    assert isinstance(row["community_id"], int), "community_id must be int"
    assert "pagerank" in row, "Missing pagerank column"


def test_louvain_community_count():
    community_ids = set()
    with open("output_jsonl/vertices_enriched.jsonl") as f:
        for line in f:
            community_ids.add(json.loads(line)["community_id"])
    assert len(community_ids) > 10, f"Too few communities: {len(community_ids)}"
    print(f"Total communities: {len(community_ids)}")


def test_all_deliverables_exist():
    required = [
        "output_jsonl/vertices_enriched.jsonl",
        "output_jsonl/pagerank_top100.jsonl",
        "output_jsonl/community_summary.jsonl",
        "output_jsonl/scalability_results.csv",
        "output_jsonl/partition_results.csv",
        "figures/scaling_curve.png",
        "figures/partition_comparison.png",
        "figures/pagerank_distribution.png",
        "figures/community_size_distribution.png",
    ]
    missing = [p for p in required if not pathlib.Path(p).exists()]
    assert not missing, f"Missing deliverables: {missing}"


def test_enriched_vertex_count():
    count = sum(1 for _ in open("output_jsonl/vertices_enriched.jsonl"))
    with open("output_jsonl/vertices.jsonl") as f:
        original = sum(1 for _ in f)
    assert count == original, f"Row count mismatch: enriched={count}, original={original}"


def test_interface_types():
    with open("output_jsonl/vertices_enriched.jsonl") as f:
        row = json.loads(f.readline())
    assert isinstance(row["pagerank"], float), "pagerank must be double/float"
    assert isinstance(row["community_id"], int), "community_id must be int"
