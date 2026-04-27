# Graph Analytics Member B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对已有的图谱数据（153,331节点 / 114,896边）运行 PageRank 和 Louvain 社区发现算法，产出 `vertices_enriched.jsonl`，并完成三组 Scalability 实验和可视化。

**Architecture:** 用 PySpark + GraphFrames 加载图数据并运行 PageRank；用 NetworkX 在单机内存中运行 Louvain 社区发现（15万节点完全可容纳）；最终将两份结果合并写回 `output_jsonl/vertices_enriched.jsonl` 供成员C使用；单独的 scalability_test.py 采样三个规模子集重复实验并记录耗时。

**Tech Stack:** Python 3.x, PySpark 3.x, graphframes 0.8+, networkx 3.x, python-louvain / networkx.community, pandas, matplotlib, seaborn

---

## File Structure

| Path | 职责 |
|------|------|
| `graph_analytics.py` | 主脚本：加载图、运行 PageRank、运行 Louvain、合并结果、保存 enriched 节点表 |
| `scalability_test.py` | 扩展性实验：构造 1/4、1/2、全量子集，分别计时跑 PageRank 和 Louvain，记录结果 |
| `visualization.py` | 绘图：scaling 曲线、分区策略对比、PageRank 分布直方图、社区大小分布 |
| `output_jsonl/vertices_enriched.jsonl` | 输出：节点表 + pagerank（double）+ community_id（int） |
| `output_jsonl/pagerank_top100.jsonl` | 输出：PageRank 最高100个节点 |
| `output_jsonl/community_summary.jsonl` | 输出：每个社区的统计信息 |
| `output_jsonl/scalability_results.csv` | 输出：每组实验的耗时数据 |
| `figures/` | 输出：所有 PNG 图表 |
| `tests/test_graph_analytics.py` | 单元测试：验证 PageRank 结果格式和 Louvain 映射正确性 |

---

## Task 1: 环境验证与数据加载

**Files:**
- Create: `graph_analytics.py`
- Create: `tests/test_graph_analytics.py`

- [ ] **Step 1: 验证依赖是否安装**

```bash
python -c "import pyspark; import graphframes; import networkx; print('OK')"
```

Expected: `OK`
如果报 `ModuleNotFoundError`，安装缺失包：
```bash
pip install pyspark graphframes networkx matplotlib seaborn pandas
```

- [ ] **Step 2: 写数据加载的失败测试**

```python
# tests/test_graph_analytics.py
import json, pathlib

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
```

- [ ] **Step 3: 运行测试，确认当前数据通过**

```bash
pytest tests/test_graph_analytics.py -v
```

Expected: 3 tests PASS（如果有悬空边，先记录数量，再决定是否过滤）

- [ ] **Step 4: 写 Spark 会话和数据加载函数**

```python
# graph_analytics.py
import time
from pyspark.sql import SparkSession

def create_spark():
    return (SparkSession.builder
            .appName("GraphRAG-Analytics")
            .config("spark.jars.packages", "graphframes:graphframes:0.8.2-spark3.2-s_2.12")
            .config("spark.sql.shuffle.partitions", "200")
            .getOrCreate())

def load_graph(spark, vertices_path="output_jsonl/vertices.jsonl",
               edges_path="output_jsonl/edges.jsonl"):
    from graphframes import GraphFrame
    v = spark.read.json(vertices_path)
    e = spark.read.json(edges_path)
    return GraphFrame(v, e)
```

- [ ] **Step 5: 手动验证加载正确**

```bash
python -c "
from graph_analytics import create_spark, load_graph
spark = create_spark()
g = load_graph(spark)
print('vertices:', g.vertices.count())
print('edges:', g.edges.count())
spark.stop()
"
```

Expected:
```
vertices: 153331
edges: 114896
```

- [ ] **Step 6: Commit**

```bash
git add graph_analytics.py tests/test_graph_analytics.py
git commit -m "feat: add spark session setup and data loading with schema tests"
```

---

## Task 2: PageRank 计算

**Files:**
- Modify: `graph_analytics.py`
- Modify: `tests/test_graph_analytics.py`

- [ ] **Step 1: 写 PageRank 输出格式的失败测试**

在 `tests/test_graph_analytics.py` 末尾追加：

```python
import pathlib

def test_pagerank_output_exists():
    p = pathlib.Path("output_jsonl/vertices_with_pagerank.jsonl")
    assert p.exists(), "Run graph_analytics.py first"

def test_pagerank_output_schema():
    with open("output_jsonl/vertices_with_pagerank.jsonl") as f:
        row = json.loads(f.readline())
    assert "pagerank" in row, "Missing pagerank column"
    assert isinstance(row["pagerank"], float), "pagerank must be float"
    assert row["pagerank"] >= 0.0
```

- [ ] **Step 2: 运行，确认测试失败（文件尚未存在）**

```bash
pytest tests/test_graph_analytics.py::test_pagerank_output_exists -v
```

Expected: FAIL with `AssertionError: Run graph_analytics.py first`

- [ ] **Step 3: 实现 PageRank 函数**

在 `graph_analytics.py` 中追加：

```python
def run_pagerank(g, reset_prob=0.15, max_iter=10):
    """Returns vertices DataFrame with pagerank column added."""
    t0 = time.time()
    results = g.pageRank(resetProbability=reset_prob, maxIter=max_iter)
    elapsed = time.time() - t0
    print(f"[PageRank] maxIter={max_iter}, time={elapsed:.1f}s")
    return results.vertices, elapsed

def save_pagerank(vertices_pr, out_path="output_jsonl/vertices_with_pagerank"):
    vertices_pr.write.mode("overwrite").json(out_path)
    print(f"Saved pagerank results to {out_path}/")
```

- [ ] **Step 4: 写主入口调用 PageRank**

在 `graph_analytics.py` 末尾追加：

```python
if __name__ == "__main__":
    import os, json
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
```

- [ ] **Step 5: 运行脚本**

```bash
python graph_analytics.py
```

Expected output 包含：
```
[PageRank] maxIter=10, time=...s
=== Top 10 PageRank Nodes ===
```

- [ ] **Step 6: 将分区输出合并为单个 jsonl（供后续使用）**

```bash
python -c "
import os, glob, json

parts = sorted(glob.glob('output_jsonl/vertices_with_pagerank/*.json'))
with open('output_jsonl/vertices_with_pagerank.jsonl', 'w') as out:
    for p in parts:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.write(line + '\n')
print('Done')
"
```

- [ ] **Step 7: 运行 PageRank 测试，确认通过**

```bash
pytest tests/test_graph_analytics.py::test_pagerank_output_exists tests/test_graph_analytics.py::test_pagerank_output_schema -v
```

Expected: 2 tests PASS

- [ ] **Step 8: 保存 Top 100 节点**

```bash
python -c "
import json

rows = []
with open('output_jsonl/vertices_with_pagerank.jsonl') as f:
    for line in f:
        rows.append(json.loads(line))

top100 = sorted(rows, key=lambda x: x['pagerank'], reverse=True)[:100]
with open('output_jsonl/pagerank_top100.jsonl', 'w') as out:
    for r in top100:
        out.write(json.dumps(r) + '\n')
print('Top 1:', top100[0]['name'], top100[0]['pagerank'])
"
```

- [ ] **Step 9: Commit**

```bash
git add graph_analytics.py tests/test_graph_analytics.py output_jsonl/pagerank_top100.jsonl
git commit -m "feat: implement PageRank and save enriched vertices + top100"
```

---

## Task 3: Louvain 社区发现（NetworkX 方案）

**Files:**
- Modify: `graph_analytics.py`
- Modify: `tests/test_graph_analytics.py`

- [ ] **Step 1: 写 Louvain 输出格式的失败测试**

在 `tests/test_graph_analytics.py` 末尾追加：

```python
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
    # 应该有多个社区，不应该全部归为1个
    assert len(community_ids) > 10, f"Too few communities: {len(community_ids)}"
    print(f"Total communities: {len(community_ids)}")
```

- [ ] **Step 2: 运行，确认失败（文件尚未存在）**

```bash
pytest tests/test_graph_analytics.py::test_louvain_output_schema -v
```

Expected: FAIL with `FileNotFoundError` 或 `AssertionError`

- [ ] **Step 3: 实现 Louvain 函数（NetworkX）**

在 `graph_analytics.py` 追加：

```python
def run_louvain_networkx(edges_path="output_jsonl/edges.jsonl", seed=42):
    """Run Louvain on NetworkX graph. Returns {node_id: community_id} dict."""
    import networkx as nx
    import json as _json

    t0 = time.time()
    G = nx.Graph()
    with open(edges_path) as f:
        for line in f:
            e = _json.loads(line)
            G.add_edge(e["src"], e["dst"])

    communities = nx.community.louvain_communities(G, seed=seed)
    elapsed = time.time() - t0
    print(f"[Louvain] communities={len(communities)}, time={elapsed:.1f}s")

    node_to_community = {}
    for cid, members in enumerate(communities):
        for node in members:
            node_to_community[node] = cid
    return node_to_community, elapsed
```

- [ ] **Step 4: 实现 vertices_enriched 合并与保存**

在 `graph_analytics.py` 追加：

```python
def merge_and_save_enriched(pagerank_path="output_jsonl/vertices_with_pagerank.jsonl",
                             community_map=None,
                             out_path="output_jsonl/vertices_enriched.jsonl"):
    import json as _json

    with open(pagerank_path) as f_in, open(out_path, "w") as f_out:
        for line in f_in:
            row = _json.loads(line)
            node_id = row["id"]
            row["community_id"] = int(community_map.get(node_id, -1))
            f_out.write(_json.dumps(row) + "\n")
    print(f"Saved enriched vertices to {out_path}")
```

- [ ] **Step 5: 在主入口追加 Louvain 调用**

将 `graph_analytics.py` 的 `if __name__ == "__main__":` 块更新为：

```python
if __name__ == "__main__":
    import os, json
    spark = create_spark()
    spark.sparkContext.setCheckpointDir("/tmp/graphframes_checkpoints")

    g = load_graph(spark)

    # PageRank
    v_pr, pr_time = run_pagerank(g, max_iter=10)
    save_pagerank(v_pr)
    spark.stop()

    # 合并 Spark 分区输出（如尚未合并）
    import glob
    if not os.path.exists("output_jsonl/vertices_with_pagerank.jsonl"):
        parts = sorted(glob.glob("output_jsonl/vertices_with_pagerank/*.json"))
        with open("output_jsonl/vertices_with_pagerank.jsonl", "w") as out:
            for p in parts:
                with open(p) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            out.write(line + "\n")

    # Louvain（NetworkX，单机）
    community_map, louvain_time = run_louvain_networkx()
    merge_and_save_enriched(community_map=community_map)

    # Top 10 PageRank 质量检查
    import json
    rows = []
    with open("output_jsonl/vertices_enriched.jsonl") as f:
        for line in f:
            rows.append(json.loads(line))
    top10 = sorted(rows, key=lambda x: x["pagerank"], reverse=True)[:10]
    print("\n=== Top 10 PageRank Nodes ===")
    for r in top10:
        print(f"  [{r['community_id']}] {r['name']}: {r['pagerank']:.4f}")
```

- [ ] **Step 6: 运行完整脚本**

```bash
python graph_analytics.py
```

Expected：看到 `[Louvain] communities=... time=...s` 以及 Top 10 列表

- [ ] **Step 7: 运行 Louvain 测试**

```bash
pytest tests/test_graph_analytics.py -v
```

Expected: All tests PASS

- [ ] **Step 8: 生成 community_summary.jsonl**

```bash
python -c "
import json
from collections import defaultdict

communities = defaultdict(list)
with open('output_jsonl/vertices_enriched.jsonl') as f:
    for line in f:
        row = json.loads(line)
        communities[row['community_id']].append(row['name'])

with open('output_jsonl/community_summary.jsonl', 'w') as out:
    for cid, members in sorted(communities.items(), key=lambda x: -len(x[1])):
        out.write(json.dumps({
            'community_id': cid,
            'size': len(members),
            'top_members': members[:5]
        }) + '\n')

print(f'Total communities: {len(communities)}')
print('Largest:')
largest = max(communities.items(), key=lambda x: len(x[1]))
print(f'  community {largest[0]}: {len(largest[1])} nodes, e.g. {largest[1][:3]}')
"
```

- [ ] **Step 9: Commit**

```bash
git add graph_analytics.py tests/test_graph_analytics.py \
        output_jsonl/vertices_enriched.jsonl \
        output_jsonl/community_summary.jsonl
git commit -m "feat: add Louvain community detection and merge into vertices_enriched"
```

---

## Task 4: Scalability 实验

**Files:**
- Create: `scalability_test.py`

- [ ] **Step 1: 写采样子集函数**

```python
# scalability_test.py
import json, random, time, csv, os

def sample_subgraph(fraction, seed=42,
                    vertices_path="output_jsonl/vertices.jsonl",
                    edges_path="output_jsonl/edges.jsonl"):
    """返回 (sampled_vertices list, sampled_edges list)"""
    random.seed(seed)
    all_vertices = []
    with open(vertices_path) as f:
        for line in f:
            all_vertices.append(json.loads(line))

    n = int(len(all_vertices) * fraction)
    sampled = random.sample(all_vertices, n)
    sampled_ids = {v["id"] for v in sampled}

    sampled_edges = []
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            if e["src"] in sampled_ids and e["dst"] in sampled_ids:
                sampled_edges.append(e)

    print(f"[Sample {fraction}] vertices={len(sampled)}, edges={len(sampled_edges)}")
    return sampled, sampled_edges
```

- [ ] **Step 2: 写 PageRank 计时函数（Spark）**

在 `scalability_test.py` 追加：

```python
def time_pagerank_spark(vertices, edges, max_iter=10):
    from pyspark.sql import SparkSession
    from graphframes import GraphFrame
    import tempfile, os

    spark = (SparkSession.builder
             .appName("ScalabilityTest")
             .config("spark.jars.packages", "graphframes:graphframes:0.8.2-spark3.2-s_2.12")
             .config("spark.sql.shuffle.partitions", "100")
             .getOrCreate())
    spark.sparkContext.setCheckpointDir("/tmp/sc_checkpoints")

    v_df = spark.createDataFrame(vertices)
    e_df = spark.createDataFrame(edges)
    g = GraphFrame(v_df, e_df)

    t0 = time.time()
    results = g.pageRank(resetProbability=0.15, maxIter=max_iter)
    results.vertices.count()  # trigger action
    elapsed = time.time() - t0
    spark.stop()
    return elapsed
```

- [ ] **Step 3: 写 Louvain 计时函数（NetworkX）**

在 `scalability_test.py` 追加：

```python
def time_louvain_networkx(edges, seed=42):
    import networkx as nx
    G = nx.Graph()
    for e in edges:
        G.add_edge(e["src"], e["dst"])
    t0 = time.time()
    communities = nx.community.louvain_communities(G, seed=seed)
    elapsed = time.time() - t0
    print(f"  Louvain communities={len(communities)}, time={elapsed:.1f}s")
    return elapsed
```

- [ ] **Step 4: 写实验主循环**

在 `scalability_test.py` 追加：

```python
def run_experiments():
    os.makedirs("output_jsonl", exist_ok=True)
    results = []

    for fraction, label in [(0.25, "25%"), (0.5, "50%"), (1.0, "100%")]:
        print(f"\n=== Scale: {label} ===")
        vertices, edges = sample_subgraph(fraction)

        pr_time = time_pagerank_spark(vertices, edges, max_iter=10)
        louvain_time = time_louvain_networkx(edges)

        results.append({
            "fraction": fraction,
            "label": label,
            "num_vertices": len(vertices),
            "num_edges": len(edges),
            "pagerank_sec": round(pr_time, 2),
            "louvain_sec": round(louvain_time, 2),
        })
        print(f"  PageRank: {pr_time:.1f}s, Louvain: {louvain_time:.1f}s")

    with open("output_jsonl/scalability_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print("\nSaved to output_jsonl/scalability_results.csv")
    return results

if __name__ == "__main__":
    run_experiments()
```

- [ ] **Step 5: 运行实验（预计需要几分钟）**

```bash
python scalability_test.py
```

Expected：每组打印节点数、边数和耗时，最终写入 CSV

- [ ] **Step 6: 验证 CSV 输出**

```bash
python -c "
import csv
with open('output_jsonl/scalability_results.csv') as f:
    for row in csv.DictReader(f):
        print(row)
"
```

Expected：3行，fraction 分别为 0.25 / 0.5 / 1.0

- [ ] **Step 7: Commit**

```bash
git add scalability_test.py output_jsonl/scalability_results.csv
git commit -m "feat: add scalability experiment script with PageRank and Louvain timing"
```

---

## Task 5: 分区优化对比实验

**Files:**
- Modify: `scalability_test.py`

- [ ] **Step 1: 添加不同分区策略的 PageRank 计时**

在 `scalability_test.py` 中追加：

```python
def time_pagerank_with_partitions(vertices, edges, num_partitions, max_iter=10):
    from pyspark.sql import SparkSession
    from graphframes import GraphFrame

    spark = (SparkSession.builder
             .appName(f"PartitionTest-{num_partitions}")
             .config("spark.jars.packages", "graphframes:graphframes:0.8.2-spark3.2-s_2.12")
             .config("spark.sql.shuffle.partitions", str(num_partitions))
             .getOrCreate())
    spark.sparkContext.setCheckpointDir("/tmp/sc_checkpoints")

    v_df = spark.createDataFrame(vertices).repartition(num_partitions)
    e_df = spark.createDataFrame(edges).repartition(num_partitions)
    g = GraphFrame(v_df, e_df)

    t0 = time.time()
    results = g.pageRank(resetProbability=0.15, maxIter=max_iter)
    results.vertices.count()
    elapsed = time.time() - t0
    spark.stop()
    return elapsed

def run_partition_experiments():
    print("\n=== Partition Strategy Experiment (full graph) ===")
    vertices, edges = sample_subgraph(1.0)
    partition_results = []

    for n_parts, label in [(50, "50 partitions"), (100, "100 partitions"), (200, "200 partitions")]:
        t = time_pagerank_with_partitions(vertices, edges, num_partitions=n_parts)
        partition_results.append({"partitions": n_parts, "label": label, "pagerank_sec": round(t, 2)})
        print(f"  {label}: {t:.1f}s")

    with open("output_jsonl/partition_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=partition_results[0].keys())
        writer.writeheader()
        writer.writerows(partition_results)
    print("Saved to output_jsonl/partition_results.csv")
    return partition_results
```

- [ ] **Step 2: 在主入口追加调用**

将 `scalability_test.py` 的 `if __name__ == "__main__":` 改为：

```python
if __name__ == "__main__":
    run_experiments()
    run_partition_experiments()
```

- [ ] **Step 3: 运行**

```bash
python scalability_test.py
```

Expected：额外输出三组分区实验的耗时，写入 `output_jsonl/partition_results.csv`

- [ ] **Step 4: Commit**

```bash
git add scalability_test.py output_jsonl/partition_results.csv
git commit -m "feat: add partition strategy comparison experiment"
```

---

## Task 6: 可视化

**Files:**
- Create: `visualization.py`
- Create: `figures/` (目录)

- [ ] **Step 1: 创建图表目录**

```bash
mkdir -p figures
```

- [ ] **Step 2: 实现 scaling 曲线图（图1）**

```python
# visualization.py
import csv, json
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")  # 非交互式后端

def plot_scaling_curve():
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
```

- [ ] **Step 3: 实现分区策略对比图（图2）**

在 `visualization.py` 追加：

```python
def plot_partition_comparison():
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
```

- [ ] **Step 4: 实现 PageRank 分布直方图（图3）**

在 `visualization.py` 追加：

```python
def plot_pagerank_distribution():
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
```

- [ ] **Step 5: 实现社区大小分布图（图4）**

在 `visualization.py` 追加：

```python
def plot_community_size_distribution():
    from collections import Counter

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
    print(f"Saved figures/community_size_distribution.png")

if __name__ == "__main__":
    plot_scaling_curve()
    plot_partition_comparison()
    plot_pagerank_distribution()
    plot_community_size_distribution()
    print("\nAll figures saved to figures/")
```

- [ ] **Step 6: 运行可视化脚本**

```bash
python visualization.py
```

Expected：生成 4 个 PNG 文件，无报错

- [ ] **Step 7: 验证图表文件存在**

```bash
ls -lh figures/
```

Expected：
```
scaling_curve.png
partition_comparison.png
pagerank_distribution.png
community_size_distribution.png
```

- [ ] **Step 8: Commit**

```bash
git add visualization.py figures/
git commit -m "feat: add visualization for scaling curve, partition comparison, and distributions"
```

---

## Task 7: 数据接口交付验证

**Files:**
- Modify: `tests/test_graph_analytics.py`

- [ ] **Step 1: 写交付物完整性测试**

在 `tests/test_graph_analytics.py` 末尾追加：

```python
import pathlib

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
```

- [ ] **Step 2: 运行所有测试**

```bash
pytest tests/test_graph_analytics.py -v
```

Expected: All tests PASS

- [ ] **Step 3: Final Commit**

```bash
git add tests/test_graph_analytics.py
git commit -m "test: add deliverable completeness and interface type validation"
```

---

## 输出交付物清单

| 文件 | 说明 | 成员C/D 依赖 |
|------|------|-------------|
| `output_jsonl/vertices_enriched.jsonl` | pagerank(float) + community_id(int) | 成员C：检索排序 |
| `output_jsonl/pagerank_top100.jsonl` | Top 100 节点 | 演示/质量检查 |
| `output_jsonl/community_summary.jsonl` | 社区统计（社区ID、大小、代表实体）| 成员C/D |
| `output_jsonl/scalability_results.csv` | 3组规模实验的耗时数据 | 成员D：报告图表 |
| `output_jsonl/partition_results.csv` | 分区策略实验耗时数据 | 成员D |
| `figures/*.png` | 4张性能/分布图表 | 成员D：PPT/报告 |

---

## Self-Review

**Spec coverage check:**
- [x] PageRank（Task 2）
- [x] Louvain 社区发现（Task 3）
- [x] Scalability 实验 1/4 / 1/2 / 全量（Task 4）
- [x] 分区优化对比（Task 5）
- [x] 可视化 4 张图（Task 6）
- [x] vertices_enriched.jsonl 输出（Task 3）
- [x] pagerank_top100.jsonl（Task 2）
- [x] community_summary.jsonl（Task 3）
- [x] 接口类型验证（Task 7）

**Placeholder scan:** 无 TBD / TODO / "similar to" 表述，所有代码块均为可直接运行的完整代码。

**Type consistency:** `pagerank` 全程为 `float`，`community_id` 全程为 `int`，文件路径在所有任务中保持一致。
