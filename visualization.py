import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt


# Default data version for visualization; can be overridden via CLI arg or env var
_DEFAULT_VERSION = os.environ.get("GRAPH_RAG_VERSION", "v5")


def _cfg(version=None):
    """Return a Config for the given data version."""
    from graph_rag import Config
    return Config(data_version=version or _DEFAULT_VERSION)


def plot_scaling_curve():
    """Plot algorithm runtime vs. graph scale (Figure 1)."""
    path = "output_jsonl/scalability_results.csv"
    if not os.path.exists(path):
        print(f"Skipping scaling curve: {path} not found (run scalability_test.py first)")
        return
    rows = []
    with open(path) as f:
        rows = list(csv.DictReader(f))

    labels = [r["label"] for r in rows]
    n_vertices = [int(r["num_vertices"]) for r in rows]
    pr_times = [float(r["pagerank_sec"]) for r in rows]
    lv_times = [float(r["louvain_sec"]) for r in rows]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(n_vertices, pr_times, "o-", label="PageRank", color="steelblue")
    ax.plot(n_vertices, lv_times, "s-", label="Louvain (Networkit)", color="coral")
    ax.set_xlabel("Number of Vertices")
    ax.set_ylabel("Runtime (seconds)")
    ax.set_title("Algorithm Runtime vs. Graph Scale")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("figures/scaling_curve.png", dpi=150)
    plt.close()
    print("Saved figures/scaling_curve.png")


def plot_partition_comparison():
    """Plot PageRank runtime by partition strategy (Figure 2)."""
    path = "output_jsonl/partition_results.csv"
    if not os.path.exists(path):
        print(f"Skipping partition comparison: {path} not found (run scalability_test.py first)")
        return
    rows = []
    with open(path) as f:
        rows = list(csv.DictReader(f))

    labels = [r["label"] for r in rows]
    times = [float(r["pagerank_sec"]) for r in rows]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, times, color=["#4C72B0", "#55A868", "#C44E52"])
    ax.set_ylabel("PageRank Runtime (seconds)")
    ax.set_title("PageRank Runtime by Partition Strategy")
    for bar, t in zip(bars, times):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                f"{t:.1f}s", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.savefig("figures/partition_comparison.png", dpi=150)
    plt.close()
    print("Saved figures/partition_comparison.png")


def plot_pagerank_distribution():
    """Plot PageRank score distribution (Figure 3)."""
    import numpy as np

    scores = []
    with open(_cfg().enriched_jsonl) as f:
        for line in f:
            scores.append(json.loads(line)["pagerank"])

    scores = np.array(scores)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    axes[0].hist(scores, bins=100, color="steelblue", edgecolor="none")
    axes[0].set_xlabel("PageRank Score")
    axes[0].set_ylabel("Count")
    axes[0].set_title("PageRank Distribution (linear)")

    axes[1].hist(scores[scores > 0], bins=100, log=True, color="steelblue", edgecolor="none")
    axes[1].set_xlabel("PageRank Score")
    axes[1].set_ylabel("Count (log scale)")
    axes[1].set_title("PageRank Distribution (log scale)")

    plt.tight_layout()
    plt.savefig("figures/pagerank_distribution.png", dpi=150)
    plt.close()
    print(f"Saved figures/pagerank_distribution.png  |  median={np.median(scores):.6f}  max={scores.max():.4f}")


def plot_community_size_distribution():
    """Plot community size distribution (Figure 4)."""
    sizes = []
    with open(_cfg().community_summary) as f:
        for line in f:
            sizes.append(json.loads(line)["size"])

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(sizes, bins=50, color="coral", edgecolor="none")
    ax.set_xlabel("Community Size (number of nodes)")
    ax.set_ylabel("Number of Communities")
    ax.set_title(f"Community Size Distribution  (total {len(sizes)} communities)")
    ax.set_yscale("log")
    plt.tight_layout()
    plt.savefig("figures/community_size_distribution.png", dpi=150)
    plt.close()
    print("Saved figures/community_size_distribution.png")


def plot_entity_mentions_vs_pagerank():
    """Plot entity chunk mention count vs PageRank score (Figure 5)."""
    import numpy as np

    # Load pagerank scores
    pr_map = {}
    with open(_cfg().enriched_jsonl) as f:
        for line in f:
            r = json.loads(line)
            pr_map[r["id"]] = r.get("pagerank", 0.0)

    # Load chunk mention counts
    mentions = []
    with open(_cfg().entity_chunk_mentions) as f:
        for line in f:
            r = json.loads(line)
            eid = r.get("entity_id")
            mentions.append({
                "entity_id": eid,
                "entity_name": r.get("entity_name", ""),
                "chunk_mention_count": r.get("chunk_mention_count", 0),
                "pagerank": pr_map.get(eid, 0.0),
            })

    if not mentions:
        print("No entity_chunk_mentions data found, skipping plot.")
        return

    prs = np.array([m["pagerank"] for m in mentions])
    counts = np.array([m["chunk_mention_count"] for m in mentions])

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(prs, counts, alpha=0.4, s=15, color="steelblue", edgecolor="none")
    ax.set_xlabel("PageRank Score")
    ax.set_ylabel("Chunk Mention Count")
    ax.set_title("Entity Text Coverage vs. Graph Importance")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)

    # Annotate top outliers
    sorted_by_pr = sorted(mentions, key=lambda x: x["pagerank"], reverse=True)[:5]
    for m in sorted_by_pr:
        ax.annotate(m["entity_name"][:25],
                    xy=(m["pagerank"], m["chunk_mention_count"]),
                    fontsize=7, alpha=0.7)

    plt.tight_layout()
    plt.savefig("figures/entity_mentions_vs_pagerank.png", dpi=150)
    plt.close()
    print(f"Saved figures/entity_mentions_vs_pagerank.png  |  n={len(mentions)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GraphRAG Visualization")
    parser.add_argument("--data-version", default="v5",
                        help="Data version for file paths (default: v5)")
    args = parser.parse_args()
    _DEFAULT_VERSION = args.data_version

    os.makedirs("figures", exist_ok=True)
    plot_scaling_curve()
    plot_partition_comparison()
    plot_pagerank_distribution()
    plot_community_size_distribution()
    plot_entity_mentions_vs_pagerank()
    print(f"\nAll figures saved to figures/ (data version: {_DEFAULT_VERSION})")
