import json
import pathlib

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
