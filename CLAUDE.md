# CLAUDE.md — 项目上下文指南

## 项目概述

Graph-RAG 是一个基于知识图谱的 RAG（Retrieval-Augmented Generation）系统。本项目（Member B 部分）负责**图分析**环节：在知识图谱上运行 PageRank、Louvain 社区检测等算法，并做可扩展性实验与可视化。

## 技术栈

- **Python 3.12**（conda 环境 `graph_rag`）
- **PySpark 3.5.1** + **GraphFrames 0.8.3**（分布式图计算）
- **NetworkX 3.3**（单机社区检测）
- **Matplotlib / Seaborn**（可视化）
- **Pytest 8.2.2**（测试）

## 环境与执行

```bash
# 必须使用此 Python 解释器
/opt/anaconda3/envs/graph_rag/bin/python

# 运行全流水线
/opt/anaconda3/envs/graph_rag/bin/python graph_analytics.py

# 运行可扩展性实验
/opt/anaconda3/envs/graph_rag/bin/python scalability_test.py

# 运行可视化
/opt/anaconda3/envs/graph_rag/bin/python visualization.py

# 运行测试
/opt/anaconda3/envs/graph_rag/bin/python -m pytest tests/ -v
```

## 项目结构

```
graph-RAG/
├── graph_rag/                    # 核心包（重构后的模块化代码）
│   ├── __init__.py               # 暴露 Config, Pipeline
│   ├── config.py                 # 集中配置：所有路径和算法参数
│   ├── spark_utils.py            # Spark 会话创建（含 checkpoint 设置）
│   ├── io_utils.py               # 文件 I/O：merge_spark_parts, load_graph, read_jsonl, write_jsonl
│   ├── algorithms/
│   │   ├── __init__.py           # 暴露 pagerank 和 community 核心函数
│   │   ├── pagerank.py           # PageRank：run_pagerank, save_pagerank, extract_top_n, time_pagerank_*
│   │   └── community.py          # 社区检测：run_louvain_networkx, merge_and_save_enriched, time_louvain_networkx
│   ├── pipeline.py               # Pipeline 类：可分步或一键运行
│   └── scalability.py            # 可扩展性测试：sample_subgraph, run_scaling/partition_experiments
├── graph_analytics.py            # 入口：Pipeline().run_all()
├── scalability_test.py           # 入口：可扩展性 + 分区实验
├── visualization.py              # 四张图的生成脚本（独立，未纳入包）
├── tests/
│   └── test_graph_analytics.py   # 导入测试 + 输出完整性测试
├── output_jsonl/                 # 数据目录（由流水线生成）
│   ├── vertices.jsonl            # 输入：图节点（id, name, type）
│   ├── edges.jsonl               # 输入：图边（src, dst, relation, source）
│   ├── vertices_with_pagerank/   # Spark 输出的分区 JSON
│   ├── vertices_with_pagerank.jsonl  # 合并后的 PageRank 结果
│   ├── pagerank_top100.jsonl     # Top 100 节点
│   ├── vertices_enriched.jsonl   # 合并 PageRank + 社区 ID 的节点
│   ├── community_summary.jsonl   # 社区摘要
│   ├── scalability_results.csv   # 可扩展性实验结果
│   └── partition_results.csv     # 分区策略实验结果
├── figures/                      # 可视化输出
└── requirements.txt
```

## 核心模块说明

### Config（`graph_rag/config.py`）
- 使用 `@dataclass`，所有路径和算法参数集中在一处
- 实验时只需 `Config(max_iter=20, reset_prob=0.1)` 即可覆盖
- 不要在各模块中硬编码路径或参数

### Pipeline（`graph_rag/pipeline.py`）
- `Pipeline(cfg)` 接受可选的 Config 实例
- 分步调用：`p.run_pagerank_step()` / `p.run_louvain_step()` / `p.run_quality_check()`
- 一键运行：`p.run_all()`

### Algorithms（`graph_rag/algorithms/`）
- **pagerank.py**：PageRank 计算与计时函数。`time_pagerank_spark` 和 `time_pagerank_with_partitions` 会自建 SparkSession（用于隔离的 benchmark）
- **community.py**：Louvain 社区检测与 enriched 合并。`run_louvain_networkx` 从文件读边，`time_louvain_networkx` 从内存边列表运行

### Scalability（`graph_rag/scalability.py`）
- `sample_subgraph()`：按比例采样子图
- `run_scaling_experiments()`：不同规模下的 PageRank + Louvain 计时
- `run_partition_experiments()`：不同分区数下的 PageRank 计时

## 数据格式

### vertices.jsonl
```json
{"id": "entity_001", "name": "Python", "type": "language"}
```

### edges.jsonl
```json
{"src": "entity_001", "dst": "entity_002", "relation": "used_by", "source": "wikipedia"}
```

### vertices_enriched.jsonl（流水线输出）
```json
{"id": "entity_001", "name": "Python", "type": "language", "pagerank": 0.0034, "community_id": 5}
```

## 常见陷阱

1. **GraphFrames 不能 pip 安装**：0.8.3 版本未发布到 PyPI，必须通过 `spark.jars.packages` 配置加载，格式为 `graphframes:graphframes:0.8.3-spark3.5-s_2.12`。代码中已在 `create_spark()` 和各 benchmark 函数中配置好，不要尝试 `pip install graphframes==0.8.3`

2. **Python 解释器**：必须使用 `/opt/anaconda3/envs/graph_rag/bin/python`，系统默认 Python 缺少依赖

3. **Spark checkpoint**：GraphFrames 的 PageRank 需要 checkpoint 目录，`create_spark()` 已自动设置 `/tmp/graphframes_checkpoints`。自建 SparkSession 时也需要设置

4. **Spark 输出是分区文件**：`save_pagerank()` 输出的是 Spark 分区格式（`part-00000.json` 等），需要 `merge_spark_parts()` 合并成单个 `.jsonl` 文件

5. **Louvain 是单机算法**：使用 NetworkX 实现，数据量大时可能 OOM，不适合超大规模图

## 修改指南

- **改算法参数**：修改 `graph_rag/config.py` 中的 Config 默认值，或运行时传参
- **加新算法**：在 `graph_rag/algorithms/` 下新建模块，更新 `algorithms/__init__.py` 暴露接口，在 `pipeline.py` 中添加对应 step
- **加新实验**：在 `graph_rag/scalability.py` 中添加函数，更新 `scalability_test.py` 入口
- **改数据路径**：只需修改 `Config` 中的路径字段
