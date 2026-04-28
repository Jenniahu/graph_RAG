"""Centralized configuration for graph analytics."""

from dataclasses import dataclass, field


@dataclass
class Config:
    """All configurable paths and algorithm parameters in one place.

    Override any field when constructing, e.g.:
        cfg = Config(max_iter=20, reset_prob=0.1)
    """

    # --- paths ---
    vertices_path: str = "output_jsonl/vertices.jsonl"
    edges_path: str = "output_jsonl/edges.jsonl"
    output_dir: str = "output_jsonl"
    pagerank_dir: str = "output_jsonl/vertices_with_pagerank"
    pagerank_jsonl: str = "output_jsonl/vertices_with_pagerank.jsonl"
    pagerank_topn: str = "output_jsonl/pagerank_top100.jsonl"
    enriched_jsonl: str = "output_jsonl/vertices_enriched.jsonl"
    community_summary: str = "output_jsonl/community_summary.jsonl"
    scalability_csv: str = "output_jsonl/scalability_results.csv"
    partition_csv: str = "output_jsonl/partition_results.csv"
    figures_dir: str = "figures"

    # --- PageRank ---
    reset_prob: float = 0.15
    max_iter: int = 10
    top_n: int = 100

    # --- Louvain ---
    louvain_seed: int = 42

    # --- Spark ---
    app_name: str = "GraphRAG-Analytics"
    graphframes_package: str = "graphframes:graphframes:0.8.3-spark3.5-s_2.12"
    shuffle_partitions: int = 200
    checkpoint_dir: str = "/tmp/graphframes_checkpoints"

    # --- Scalability ---
    scalability_fractions: list = field(default_factory=lambda: [0.25, 0.5, 1.0])
    partition_counts: list = field(default_factory=lambda: [50, 100, 200])
    scalability_seed: int = 42
