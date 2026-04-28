PART2 Graph Analytics

0. 一句话定位

对成员A构建的知识图谱（15.3万节点 / 11.5万边）运行 PageRank 与 Louvain 算法，产出每个节点的重要性分数（pagerank）与社区归属（community_id），使下游检索能优先关注核心实体并按语义社区扩展召回；同时完成三组 Scalability 实验验证系统可扩展性。

0.1 你要在PPT强调的核心创新点（3句话讲清楚）

1. 引入 PageRank 排序：候选实体/边按 pagerank 降序排列，检索优先关注图谱核心节点（如 United States、Iran 等高分实体），避免低分噪声进入 Prompt。
2. 引入 Louvain 社区归属：划分出约 3.9 万个语义社区，检索时从 seed 实体同社区内补充 top-pagerank 近邻，提升多跳覆盖。
3. Scalability 实验验证：25%/50%/100% 三组规模 + 三种分区策略对比已完成，证明图算法模块随数据增长可扩展。

1. 输入数据（Data）

图谱结构

● data/vertices.jsonl：约 153,331 节点（id / name / type）
● data/edges.jsonl：约 114,896 边（src / dst / relation / source）
  说明：source 字段区分 seed（DBpedia 结构化）与 extracted（文本抽取）两类边

2. 关键中间产物（Artifacts）

2.1 PageRank 结果

● data/vertices_with_pagerank.jsonl：每个节点新增 pagerank（float）列
  关键参数：resetProbability=0.15、maxIter=10
● data/pagerank_top100.jsonl：PageRank 最高 100 个节点
  Top-5：United States(1286.05)、Iran(793.42)、India(746.67)、United Kingdom(689.14)、France(674.67)

2.2 Louvain 社区发现结果

● data/vertices_enriched.jsonl：在 pagerank 基础上新增 community_id（int）列
  关键参数：NetworkX louvain_communities，seed=42
  说明：共约 39,466 个社区，最大社区 2,475 节点，社区大小呈重尾分布
● data/community_summary.jsonl：每个社区的统计信息（community_id / size / top_members）
  说明：community_summary 不是直接进 LLM，而是先向量化建立 community index

3. 算法实现

3.1 PageRank（节点重要性排序）

● 框架：PySpark + GraphFrames
● API：g.pageRank(resetProbability=0.15, maxIter=10)
● 输出：vertices DataFrame 新增 pagerank 列
● 为什么要 PageRank：被大量重要实体指向的节点本身就是核心概念；检索时按 pagerank 排序可过滤低分噪声实体

3.2 Louvain 社区发现

● 框架：NetworkX（单机内存，15万节点可容纳）
● API：nx.community.louvain_communities(G, seed=42)
● 为什么要用 NetworkX 而非 Spark：GraphFrames 无内置 Louvain；15万节点单机可跑，避免分布式复杂度
  说明：如后续扩展到百万级，可迁移到 Spark 原生 Louvain 或 Neo4j GDS
● 输出：{node_id: community_id} 映射，合并写回 vertices_enriched.jsonl
● 语义验证：社区4590（波兰相关）、社区27427（澳大利亚相关）、社区386（Nashville乡村音乐相关）

4. Scalability 实验

4.1 数据规模对比

| 规模 | 节点数 | 边数 | PageRank | Louvain |
|------|--------|------|----------|---------|
| 25%  | 38,332 | 7,227 | 12.07s | 0.24s |
| 50%  | 76,665 | 29,051 | 4.62s | 1.53s |
| 100% | 153,331 | 114,896 | 62.19s | 7.29s |

  说明：采样策略为随机采样节点 + 只保留两端点均在采样集内的边

4.2 分区优化对比（全量数据）

| 分区数 | PageRank 运行时间 |
|--------|-----------------|
| 50     | 24.77s |
| 100    | 57.53s |
| 200    | 219.46s |

  结论：分区数不是越多越好，单机/小数据集场景下过多分区引入不必要的 Shuffle 开销

5. 质量验证

● PageRank 合理性：Top 实体均为国家/地理等核心概念，符合"被广泛引用"的结构特征
● PageRank 分布：长尾分布，极少数节点拥有极高分数，对数刻度下呈幂律特征
● Louvain 合理性：抽样社区内实体语义高度相关（同地区/同主题）
● 社区大小分布：重尾分布，少量大型社区对应核心领域，大量小社区为细粒度主题

6. 工程亮点（Implementation highlights）

● 分布式 + 单机混合架构：PageRank 用 Spark GraphFrames（可扩展到百万级），Louvain 用 NetworkX（15万节点单机高效）
● Scalability 实证：三组规模 + 三种分区策略，有实验数据证明可扩展性
● 接口标准化：pagerank(float) + community_id(int)，JSONL UTF-8 格式，供成员C直接读取

附录：可直接复制运行的命令块（PPT素材）

说明：下列命令假设你在项目根目录下运行。

A) 运行 PageRank + Louvain（图增强）

    python graph_analytics.py

    # 输出：
    #   output_jsonl/vertices_with_pagerank.jsonl
    #   output_jsonl/pagerank_top100.jsonl
    #   output_jsonl/vertices_enriched.jsonl

B) 运行 Scalability 实验

    python scalability_test.py

    # 输出：
    #   output_jsonl/scalability_results.csv
    #   output_jsonl/partition_results.csv

C) 生成可视化图表

    python visualization.py

    # 输出：
    #   figures/scaling_curve.png
    #   figures/partition_comparison.png
    #   figures/pagerank_distribution.png
    #   figures/community_size_distribution.png
