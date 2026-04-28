"""Main pipeline orchestration for graph analytics."""

import glob

from .config import Config
from .spark_utils import create_spark
from .io_utils import load_graph, merge_spark_parts, read_jsonl
from .algorithms.pagerank import run_pagerank, save_pagerank, extract_top_n
from .algorithms.community import run_louvain_networkx, merge_and_save_enriched


class Pipeline:
    """Orchestrates the full graph analytics pipeline.

    Each step can be called independently, or use ``run_all()`` for the
    complete workflow.

    Usage::

        from graph_rag import Pipeline

        # Default config
        Pipeline().run_all()

        # Custom config
        from graph_rag import Config
        cfg = Config(max_iter=20, reset_prob=0.1)
        Pipeline(cfg).run_all()

        # Run individual steps
        p = Pipeline()
        p.run_pagerank_step()
        p.run_louvain_step()
    """

    def __init__(self, cfg=None):
        self.cfg = cfg or Config()

    # ---- individual steps ----

    def run_pagerank_step(self):
        """Run PageRank on the graph, save results, and extract top-N."""
        cfg = self.cfg
        spark = create_spark(cfg)
        g = load_graph(spark, cfg.vertices_path, cfg.edges_path)

        v_pr, pr_time = run_pagerank(g, reset_prob=cfg.reset_prob, max_iter=cfg.max_iter)
        save_pagerank(v_pr, cfg.pagerank_dir)

        # Print Top 10
        print("\n=== Top 10 PageRank Nodes ===")
        v_pr.orderBy("pagerank", ascending=False).select("name", "pagerank").show(10, truncate=False)

        spark.stop()

        # Merge Spark partition files -> single jsonl
        if not glob.glob(cfg.pagerank_jsonl):
            merge_spark_parts(cfg.pagerank_dir, cfg.pagerank_jsonl)

        # Extract top N
        top = extract_top_n(cfg.pagerank_jsonl, n=cfg.top_n, out_path=cfg.pagerank_topn)
        if top:
            print(f"\nTop 1: {top[0]['name']}  pagerank={top[0]['pagerank']:.4f}")

        return v_pr

    def run_louvain_step(self):
        """Run Louvain community detection and merge with PageRank results."""
        cfg = self.cfg
        community_map, louvain_time = run_louvain_networkx(
            edges_path=cfg.edges_path, seed=cfg.louvain_seed
        )
        merge_and_save_enriched(
            pagerank_path=cfg.pagerank_jsonl,
            community_map=community_map,
            out_path=cfg.enriched_jsonl,
        )
        return community_map

    def run_quality_check(self):
        """Print Top 10 nodes by PageRank with community info."""
        cfg = self.cfg
        print("\n=== Top 10 PageRank Nodes (with community) ===")
        enriched_rows = read_jsonl(cfg.enriched_jsonl)
        top10 = sorted(enriched_rows, key=lambda x: x["pagerank"], reverse=True)[:10]
        for r in top10:
            print(f"  [community {r['community_id']}] {r['name']}: {r['pagerank']:.4f}")

    # ---- full pipeline ----

    def run_all(self):
        """Run the complete pipeline: PageRank -> Louvain -> quality check."""
        self.run_pagerank_step()
        self.run_louvain_step()
        self.run_quality_check()
