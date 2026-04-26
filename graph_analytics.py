import time
import glob


def create_spark():
    from pyspark.sql import SparkSession
    return (SparkSession.builder
            .appName("GraphRAG-Analytics")
            .config("spark.jars.packages",
                    "graphframes:graphframes:0.8.3-spark3.5-s_2.12")
            .config("spark.sql.shuffle.partitions", "200")
            .getOrCreate())


def load_graph(spark, vertices_path="output_jsonl/vertices.jsonl",
               edges_path="output_jsonl/edges.jsonl"):
    from graphframes import GraphFrame
    v = spark.read.json(vertices_path)
    e = spark.read.json(edges_path)
    return GraphFrame(v, e)


def run_pagerank(g, reset_prob=0.15, max_iter=10):
    """Returns vertices DataFrame with pagerank column added, and elapsed time."""
    t0 = time.time()
    results = g.pageRank(resetProbability=reset_prob, maxIter=max_iter)
    elapsed = time.time() - t0
    print(f"[PageRank] maxIter={max_iter}, time={elapsed:.1f}s")
    return results.vertices, elapsed


def save_pagerank(vertices_pr, out_dir="output_jsonl/vertices_with_pagerank"):
    vertices_pr.write.mode("overwrite").json(out_dir)
    print(f"Saved pagerank results to {out_dir}/")


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


if __name__ == "__main__":
    import json

    spark = create_spark()
    spark.sparkContext.setCheckpointDir("/tmp/graphframes_checkpoints")

    g = load_graph(spark)

    # PageRank
    v_pr, pr_time = run_pagerank(g, max_iter=10)
    save_pagerank(v_pr)

    # Print Top 10
    print("\n=== Top 10 PageRank Nodes ===")
    v_pr.orderBy("pagerank", ascending=False).select("name", "pagerank").show(10, truncate=False)

    spark.stop()

    # Merge Spark partition files -> single jsonl
    merge_spark_parts(
        "output_jsonl/vertices_with_pagerank",
        "output_jsonl/vertices_with_pagerank.jsonl"
    )

    # Save Top 100
    rows = []
    with open("output_jsonl/vertices_with_pagerank.jsonl") as f:
        for line in f:
            rows.append(json.loads(line))

    top100 = sorted(rows, key=lambda x: x["pagerank"], reverse=True)[:100]
    with open("output_jsonl/pagerank_top100.jsonl", "w") as out:
        for r in top100:
            out.write(json.dumps(r) + "\n")
    print(f"\nTop 1: {top100[0]['name']}  pagerank={top100[0]['pagerank']:.4f}")
    print(f"Saved output_jsonl/pagerank_top100.jsonl")
