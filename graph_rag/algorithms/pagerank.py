"""PageRank algorithm and top-N extraction."""

import time


def run_pagerank(g, reset_prob=0.15, max_iter=10):
    """Run PageRank on a GraphFrame.

    Args:
        g: GraphFrame instance.
        reset_prob: Reset probability (teleportation).
        max_iter: Maximum number of iterations.

    Returns:
        (vertices_df, elapsed_seconds)
    """
    t0 = time.time()
    results = g.pageRank(resetProbability=reset_prob, maxIter=max_iter)
    elapsed = time.time() - t0
    print(f"[PageRank] maxIter={max_iter}, time={elapsed:.1f}s")
    return results.vertices, elapsed


def save_pagerank(vertices_pr, out_dir="output_jsonl/vertices_with_pagerank"):
    """Save PageRank results to disk (Spark JSON format)."""
    vertices_pr.write.mode("overwrite").json(out_dir)
    print(f"Saved pagerank results to {out_dir}/")


def extract_top_n(pagerank_jsonl_path, n=100, out_path=None):
    """Extract top-N nodes by PageRank score from a merged JSONL file.

    Args:
        pagerank_jsonl_path: Path to the merged pagerank JSONL file.
        n: Number of top nodes to extract.
        out_path: If provided, write results to this JSONL file.

    Returns:
        List of top-N dicts sorted by pagerank descending.
    """
    from ..io_utils import read_jsonl, write_jsonl

    rows = read_jsonl(pagerank_jsonl_path)
    top = sorted(rows, key=lambda x: x["pagerank"], reverse=True)[:n]

    if out_path:
        write_jsonl(top, out_path)
        print(f"Saved top {n} -> {out_path}")

    return top


def time_pagerank_spark(vertices, edges, cfg=None, max_iter=10):
    """Run PageRank via Spark GraphFrames and return elapsed seconds.

    Creates its own SparkSession for isolated benchmarking.

    Args:
        vertices: List of vertex dicts.
        edges: List of edge dicts.
        cfg: Config instance (uses defaults if None).
        max_iter: PageRank iterations.

    Returns:
        Elapsed seconds.
    """
    from pyspark.sql import SparkSession
    from graphframes import GraphFrame

    if cfg is None:
        from ..config import Config
        cfg = Config()

    spark = (SparkSession.builder
             .appName("ScalabilityTest")
             .config("spark.jars.packages", cfg.graphframes_package)
             .config("spark.sql.shuffle.partitions", "100")
             .getOrCreate())
    spark.sparkContext.setCheckpointDir(cfg.checkpoint_dir)

    v_df = spark.createDataFrame(vertices)
    e_df = spark.createDataFrame(edges)
    g = GraphFrame(v_df, e_df)

    t0 = time.time()
    results = g.pageRank(resetProbability=cfg.reset_prob, maxIter=max_iter)
    results.vertices.count()  # trigger action to materialize
    elapsed = time.time() - t0

    spark.stop()
    print(f"  PageRank time={elapsed:.1f}s")
    return elapsed


def time_pagerank_with_partitions(vertices, edges, num_partitions, cfg=None, max_iter=10):
    """Run PageRank with a specific number of Spark partitions and return elapsed seconds.

    Args:
        vertices: List of vertex dicts.
        edges: List of edge dicts.
        num_partitions: Number of Spark partitions.
        cfg: Config instance (uses defaults if None).
        max_iter: PageRank iterations.

    Returns:
        Elapsed seconds.
    """
    from pyspark.sql import SparkSession
    from graphframes import GraphFrame

    if cfg is None:
        from ..config import Config
        cfg = Config()

    spark = (SparkSession.builder
             .appName(f"PartitionTest-{num_partitions}")
             .config("spark.jars.packages", cfg.graphframes_package)
             .config("spark.sql.shuffle.partitions", str(num_partitions))
             .getOrCreate())
    spark.sparkContext.setCheckpointDir(cfg.checkpoint_dir)

    v_df = spark.createDataFrame(vertices).repartition(num_partitions)
    e_df = spark.createDataFrame(edges).repartition(num_partitions)
    g = GraphFrame(v_df, e_df)

    t0 = time.time()
    results = g.pageRank(resetProbability=cfg.reset_prob, maxIter=max_iter)
    results.vertices.count()
    elapsed = time.time() - t0

    spark.stop()
    print(f"  {num_partitions} partitions: PageRank time={elapsed:.1f}s")
    return elapsed
