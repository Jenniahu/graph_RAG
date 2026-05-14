"""Main pipeline orchestration for graph analytics."""

import glob

from .config import Config
from .spark_utils import create_spark
from .io_utils import load_entity_graph, merge_spark_parts, read_jsonl, write_jsonl
from .algorithms.pagerank import run_pagerank, save_pagerank, extract_top_n
from .algorithms.community import run_louvain_networkit, merge_and_save_enriched


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
        if cfg.filter_entity_only:
            g = load_entity_graph(
                spark, cfg.vertices_path, cfg.edges_path,
                entity_edge_sources=cfg.entity_edge_sources
            )
        else:
            g = load_graph(spark, cfg.vertices_path, cfg.edges_path)

        v_pr, pr_time = run_pagerank(g, reset_prob=cfg.reset_prob, max_iter=cfg.max_iter)
        save_pagerank(v_pr, cfg.pagerank_dir)

        # Print Top 10
        print("\n=== Top 10 PageRank Nodes ===")
        v_pr.orderBy("pagerank", ascending=False).select("name", "pagerank").show(10, truncate=False)

        spark.stop()

        # Merge Spark partition files -> single jsonl (always merge if parts exist)
        if glob.glob(f"{cfg.pagerank_dir}/part-*.json"):
            merge_spark_parts(cfg.pagerank_dir, cfg.pagerank_jsonl)

        # Extract top N
        top = extract_top_n(cfg.pagerank_jsonl, n=cfg.top_n, out_path=cfg.pagerank_topn)
        if top:
            print(f"\nTop 1: {top[0]['name']}  pagerank={top[0]['pagerank']:.4f}")

        return v_pr

    def run_louvain_step(self):
        """Run Louvain community detection and merge with PageRank results."""
        cfg = self.cfg
        community_map, louvain_time = run_louvain_networkit(
            edges_path=cfg.edges_path,
            entity_edge_sources=cfg.entity_edge_sources if cfg.filter_entity_only else (),
            seed=cfg.louvain_seed,
        )
        merge_and_save_enriched(
            pagerank_path=cfg.pagerank_jsonl,
            community_map=community_map,
            out_path=cfg.enriched_jsonl,
        )
        return community_map

    def run_cross_layer_step(self):
        """Count how many chunks mention each entity (cross-layer analysis).

        Reads the full edge file, filters to chunk->entity mentions,
        and outputs entity_chunk_mentions.jsonl.
        """
        cfg = self.cfg
        spark = create_spark(cfg)
        e_all = spark.read.json(cfg.edges_path)

        mentions = e_all.filter(
            (e_all.source == cfg.mention_source) & (e_all.relation == cfg.mention_relation)
        )
        entity_counts = mentions.groupBy("dst").count()

        # Join with vertices to get entity names
        v_all = spark.read.json(cfg.vertices_path)
        entities = v_all.filter(v_all.node_type == "entity").select("id", "name")
        result = entity_counts.join(entities, entity_counts.dst == entities.id) \
            .select("id", "name", "count") \
            .withColumnRenamed("count", "chunk_mention_count")

        import json
        rows = result.collect()
        out_rows = [{"entity_id": r.id, "entity_name": r.name,
                     "chunk_mention_count": r.chunk_mention_count} for r in rows]
        write_jsonl(out_rows, cfg.entity_chunk_mentions)
        print(f"Saved entity-chunk mentions -> {cfg.entity_chunk_mentions} ({len(out_rows)} rows)")
        spark.stop()
        return out_rows

    def run_community_summary_step(self):
        """Generate community summary from enriched vertices.

        Groups entities by community_id and outputs the top members per community.
        """
        import json
        cfg = self.cfg

        # Group entities by community
        community_entities = {}  # community_id -> list of (name, pagerank)
        with open(cfg.enriched_jsonl) as f:
            for line in f:
                row = json.loads(line)
                cid = row.get("community_id", -1)
                if cid == -1:
                    continue
                if cid not in community_entities:
                    community_entities[cid] = []
                community_entities[cid].append((row.get("name", ""), row.get("pagerank", 0.0)))

        # Build summary: for each community, sort by pagerank, keep top members
        summary_rows = []
        for cid, members in community_entities.items():
            members.sort(key=lambda x: x[1], reverse=True)
            summary_rows.append({
                "community_id": cid,
                "size": len(members),
                "top_members": [m[0] for m in members[:5]],
            })

        write_jsonl(summary_rows, cfg.community_summary)
        print(f"Saved community summary -> {cfg.community_summary} ({len(summary_rows)} communities)")
        return summary_rows

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
        """Run the complete pipeline: PageRank -> Louvain -> cross-layer -> community summary -> quality check."""
        self.run_pagerank_step()
        self.run_louvain_step()
        self.run_cross_layer_step()
        self.run_community_summary_step()
        self.run_quality_check()
