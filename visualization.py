import csv
import json
import os

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt


def plot_scaling_curve():
    """Plot algorithm runtime vs. graph scale (Figure 1)."""
    rows = []
    with open("output_jsonl/scalability_results.csv") as f:
        rows = list(csv.DictReader(f))

    labels = [r["label"] for r in rows]
    n_vertices = [int(r["num_vertices"]) for r in rows]
    pr_times = [float(r["pagerank_sec"]) for r in rows]
    lv_times = [float(r["louvain_sec"]) for r in rows]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(n_vertices, pr_times, "o-", label="PageRank", color="steelblue")
    ax.plot(n_vertices, lv_times, "s-", label="Louvain (NetworkX)", color="coral")
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
    rows = []
    with open("output_jsonl/partition_results.csv") as f:
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
    with open("output_jsonl/vertices_enriched.jsonl") as f:
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
    with open("output_jsonl/community_summary.jsonl") as f:
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


if __name__ == "__main__":
    os.makedirs("figures", exist_ok=True)
    plot_scaling_curve()
    plot_partition_comparison()
    plot_pagerank_distribution()
    plot_community_size_distribution()
    print("\nAll figures saved to figures/")
