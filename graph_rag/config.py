"""Centralized configuration for graph analytics."""

from dataclasses import dataclass, field


# --- Data source profiles ---
# Each profile defines the path prefix, vertex filename, and
# entity-entity edge source values for a specific data source.
DATA_PROFILES = {
    "v4": {
        "data_prefix": "member_a/output_jsonl",
        "vertices_file": "vertices.jsonl",
        "entity_edge_sources": ("extracted", "seed"),
        "mention_source": "mention",
        "mention_relation": "mentions",
    },
    "v5": {
        "data_prefix": "member_a/output_jsonl 2",
        "vertices_file": "vertices.jsonl",
        "entity_edge_sources": ("extracted", "seed"),
        "mention_source": "mention",
        "mention_relation": "mentions",
    },
    "input": {
        "data_prefix": "input",
        "vertices_file": "nodes.jsonl",
        "entity_edge_sources": ("entity_cooccurrence",),
        "mention_source": "chunk_mention",
        "mention_relation": "mentions",
    },
}


@dataclass
class Config:
    """All configurable paths and algorithm parameters in one place.

    Override any field when constructing, e.g.:
        cfg = Config(max_iter=20, reset_prob=0.1)

    Data versions:
        v4  -> member_a/output_jsonl  (LLM-extracted triples)
        v5  -> member_a/output_jsonl 2 (LLM-extracted triples, v2)
        input -> input/  (entity co-occurrence statistics)
    """

    # --- data version ---
    data_version: str = "v5"  # "v4", "v5", or "input"
    filter_entity_only: bool = True

    # --- paths (auto-prefixed by data_version) ---
    @property
    def _profile(self):
        if self.data_version not in DATA_PROFILES:
            raise ValueError(f"Unknown data_version '{self.data_version}'. "
                             f"Choose from: {list(DATA_PROFILES.keys())}")
        return DATA_PROFILES[self.data_version]

    @property
    def data_prefix(self):
        return self._profile["data_prefix"]

    @property
    def vertices_path(self):
        return f"{self.data_prefix}/{self._profile['vertices_file']}"

    @property
    def edges_path(self):
        return f"{self.data_prefix}/edges.jsonl"

    @property
    def entity_edge_sources(self):
        return self._profile["entity_edge_sources"]

    @property
    def mention_source(self):
        return self._profile["mention_source"]

    @property
    def mention_relation(self):
        return self._profile["mention_relation"]

    output_dir: str = "output_jsonl"
    pagerank_dir: str = "output_jsonl/vertices_with_pagerank"
    pagerank_jsonl: str = "output_jsonl/vertices_with_pagerank.jsonl"
    pagerank_topn: str = "output_jsonl/pagerank_top100.jsonl"
    enriched_jsonl: str = "output_jsonl/vertices_enriched.jsonl"
    community_summary: str = "output_jsonl/community_summary.jsonl"
    scalability_csv: str = "output_jsonl/scalability_results.csv"
    partition_csv: str = "output_jsonl/partition_results.csv"
    figures_dir: str = "figures"
    entity_chunk_mentions: str = "output_jsonl/entity_chunk_mentions.jsonl"

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
