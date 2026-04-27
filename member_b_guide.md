# 成员B工作手册：图算法与分析工程师

## 一、你的角色定位

**核心职责**：负责"赋予图谱智能"

你是整个 GraphRAG  pipeline 的**图算法核心**。成员A把原始文本变成了图（vertices + edges），你的工作是让这张图"活"起来——通过图算法计算出每个节点的重要性分数和社区归属，让后续的检索和LLM生成能够优先关注到图谱中真正重要的实体和关系。

---

## 二、你接收的输入数据

数据已存放在 `output_jsonl/` 目录下，由成员A（图构建工程师）产出：

### 2.1 节点表：`vertices.jsonl`（约 15.3 万条）

```json
{"id":"bf9b2221f55182ccc3450b4ab81175715a85ec7e210b12012ae4780e1127130a","name":"International Journal of African Historical Studies","type":"person_or_work"}
```

| 字段 | 含义 |
|------|------|
| `id` | 节点唯一标识（哈希字符串） |
| `name` | 实体名称（如人名、地名、作品名） |
| `type` | 实体类型（当前统一为 `person_or_work`，后续可能细分） |

### 2.2 边表：`edges.jsonl`（约 11.5 万条）

```json
{"src":"9430075bd16ec76d3a0b0f93f21a4be996365fa90a82072c0726114ae9e01afd","dst":"c68dde7c0fa4e6efcc232982696cc76fbffd9bea95e1959d7fe78c9e011c4bcc","relation":"directed","source":"extracted"}
```

| 字段 | 含义 |
|------|------|
| `src` | 源节点ID，对应 `vertices.id` |
| `dst` | 目标节点ID，对应 `vertices.id` |
| `relation` | 关系类型（如 `directed`, `country`, `location`, `born_in` 等） |
| `source` | 边的来源：`seed`（来自DBpedia结构化数据）或 `extracted`（从文章中抽取） |

### 2.3 数据规模

- **节点数**：约 15.3 万
- **边数**：约 11.5 万
- 属于**中等规模**图数据，在单机 Spark 或小型集群上完全可以跑通，也适合做 scaling 实验。

---

## 三、你的三大核心任务

### 任务一：运行 PageRank 算法（节点重要性排序）

#### 目标
计算每个节点的 PageRank 分数，反映该实体在整个知识图谱中的"重要性"或"中心性"。分数越高，说明这个节点在图谱中越核心（比如频繁被其他实体指向、连接了多个社区等）。

#### 为什么需要这个？
在检索阶段，如果用户查询涉及多个候选实体，PageRank 分数可以作为**排序依据**——优先返回重要实体的相关信息，避免把边缘噪声实体也塞进 prompt 里。

#### 你需要做的步骤

1. **加载数据到 Spark GraphFrames**
   - 读取 `vertices.jsonl` 和 `edges.jsonl`
   - 构造 `GraphFrame(vertices, edges)` 对象

2. **运行 PageRank**
   - 调用 `GraphFrame.pageRank(resetProbability=0.15, maxIter=10)`
   - 或者尝试 `GraphX` 的 `PageRank`（如果需要更精细的参数控制）
   - 建议对比不同迭代次数（5次 vs 10次 vs 20次）对结果的影响

3. **结果整合**
   - 将 PageRank 分数作为新列 `pagerank` 写回节点表
   - 保存为 `vertices_with_pagerank.jsonl` 或 `vertices_enriched.jsonl`
   - 统计分数分布（Top-10 最重要实体是什么？中位数多少？）

4. **质量检查**
   - 看看 PageRank 最高的节点是否合理（应该是一些核心概念、著名人物、重要地点）
   - 如果最高的是明显噪声实体，检查是否有异常边（比如某个节点被大量抽取边指向）

---

### 任务二：运行 Louvain 社区发现算法（社区结构识别）

#### 目标
将图谱划分为若干个"社区"（Community），每个社区是一组紧密相连的实体集合。每个节点会被分配一个 `community_id`。

#### 为什么需要这个？
在检索时，如果用户查询命中了某个实体，我们可以**召回同一社区内的其他实体**作为上下文补充。因为同一个社区里的实体往往在语义上相关（比如都属于"某部电影相关人物"、"某个地区的历史事件"等），这能显著提升多跳推理的质量。

#### 你需要做的步骤

1. **运行 Louvain 算法**
   - Spark GraphFrames 本身**没有内置 Louvain**，你需要：
     - **方案A**：使用 GraphFrames 的 `connectedComponents` 或 `stronglyConnectedComponents` 作为简化替代（但效果较弱）
     - **方案B**：使用 GraphX 的第三方 Louvain 实现（如 `saurfang/spark-sas7bdat` 社区版本，或自己移植）
     - **方案C**：将图导出到 **Neo4j**，用 Neo4j GDS 库的 Louvain 算法跑，再把结果导回来
     - **方案D**：在单机/小集群上用 **NetworkX** 或 **igraph** 跑 Louvain（数据量15万节点可以接受），再映射回 Spark DataFrame
   - **推荐**：先尝试方案D（NetworkX Louvain）快速验证效果，如果项目要求必须全链路 Spark，再尝试方案B/C。

2. **结果整合**
   - 将社区ID作为新列 `community_id` 写回节点表
   - 保存更新后的节点表
   - 统计社区分布：一共划分出多少个社区？最大社区有多少节点？最小社区有多少节点？

3. **社区质量检查**
   - 抽样几个社区，看看里面的实体是否确实语义相关
   - 例如：一个社区里有 "Tom Hanks", "Forrest Gump", "Robert Zemeckis"，说明电影相关社区划分正确
   - 如果社区成员完全不相关，可能是算法参数需要调整

---

### 任务三：扩展性（Scalability）测试与性能分析

#### 目标
证明你的图算法模块在数据量增长时仍然高效，体现 "Scalable GraphRAG" 的项目主题。

#### 你需要做的步骤

1. **设计 Scaling 实验**

   你需要**基于已有数据**构造不同规模的子集：
   
   | 实验组 | 节点数 | 边数 | 构造方法 |
   |--------|--------|------|---------|
   | 1/4 规模 | ~3.8万 | ~2.9万 | 随机采样 25% 节点 + 保留内部边 |
   | 1/2 规模 | ~7.7万 | ~5.7万 | 随机采样 50% 节点 + 保留内部边 |
   | 全量 | ~15.3万 | ~11.5万 | 全部数据 |

   > 注意：采样节点时，只保留两个端点都在采样集合中的边，否则图会变得很稀疏。

2. **记录性能指标**

   对每种数据规模，分别运行以下算法，记录：
   
   | 指标 | 说明 |
   |------|------|
   | 运行时间（秒）| `spark.time()` 或 Python `time.time()` |
   | Shuffle 数据量 | Spark UI 中查看 |
   | 峰值内存占用 | Spark UI 或系统监控 |
   | 分区数 | 初始分区 vs 优化后分区 |

   需要测试的算法：
   - PageRank（固定 10 次迭代）
   - Louvain 社区发现（或替代方案）

3. **分区优化实验**

   这是体现你"Spark 优化能力"的关键点：
   
   - **默认分区**：直接加载数据，不做任何分区优化
   - **按类型分区**：`repartition("type")`（虽然当前 type 单一，但可以展示思路）
   - **按 degree 分区**：先计算每个节点的度数，将高度数节点均匀分散到不同分区
   - **对比结果**：记录不同分区策略下 PageRank 的运行时间差异

4. **绘制性能曲线**

   用 matplotlib 或 seaborn 画出：
   
   - **图1**：数据规模（x轴） vs 运行时间（y轴）—— 展示算法的 scaling trend
   - **图2**：分区策略（x轴，分类） vs 运行时间（y轴）—— 展示你的优化效果
   - **图3**：节点 PageRank 分布直方图 —— 展示图谱的结构特征

5. **Executor 数量变化实验（如果有多机环境）**

   如果在学校集群或本地多核机器上能调整 executor 数量：
   - 对比 1 executor vs 2 executors vs 4 executors 的运行时间
   - 画出加速比曲线（Speedup Curve），看是否接近线性加速

---

## 四、你的输出交付物

### 4.1 代码文件

| 文件 | 说明 |
|------|------|
| `graph_analytics.py` | 主分析脚本：加载图、运行 PageRank、运行 Louvain、保存结果 |
| `scalability_test.py` | 扩展性测试脚本：不同数据规模、不同分区策略的对比实验 |
| `visualization.py` | 可视化脚本：绘制性能曲线和 PageRank 分布图 |

### 4.2 数据文件（输出到 `output_jsonl/`）

| 文件 | 说明 |
|------|------|
| `vertices_enriched.jsonl` | 在原有节点基础上增加 `pagerank` 和 `community_id` 两列 |
| `pagerank_top100.jsonl` | PageRank 最高的 100 个节点（用于演示和质量检查） |
| `community_summary.jsonl` | 每个社区的统计信息（社区ID、节点数、代表实体） |

### 4.3 图表文件（输出到 `figures/` 或 `output/`）

| 图表 | 说明 |
|------|------|
| `scaling_pagerank.png` | PageRank 随数据规模的运行时间曲线 |
| `scaling_louvain.png` | Louvain 随数据规模的运行时间曲线 |
| `partition_comparison.png` | 不同分区策略的运行时间对比 |
| `pagerank_distribution.png` | 节点 PageRank 分数分布直方图 |
| `community_size_distribution.png` | 社区大小分布图 |

### 4.4 实验报告（并入最终报告的一部分）

需要包含以下章节：

- **算法选择理由**：为什么选 PageRank 和 Louvain？
- **实现细节**：Spark GraphFrames/GraphX 的关键 API 调用
- **分区优化策略**：你尝试了哪些优化？效果如何？
- **Scalability 结果**：数据量翻倍时运行时间怎么变化？加速比多少？
- **质量验证**：Top 实体是否合理？社区划分是否语义一致？

---

## 五、你与团队成员的协作接口

### 5.1 上游依赖（成员A：图构建工程师）

- **你依赖他**：`vertices.jsonl` 和 `edges.jsonl` 必须格式正确、无重复节点、无悬空边（边的 src/dst 必须都在 vertices 中）
- **需要确认**：
  - 节点 `id` 是否全局唯一？
  - 是否有自环边（src == dst）？如果有，PageRank 是否需要特殊处理？
  - `type` 字段后续是否会细分（比如分出 `person`, `location`, `organization`）？如果会，你的分区策略可以更丰富

### 5.2 下游交付（成员C：RAG检索与LLM集成工程师）

- **他依赖你**：`vertices_enriched.jsonl` 中的 `pagerank` 和 `community_id`
- **你需要给他明确的接口说明**：
  - `pagerank` 列的数据类型（建议 `double`）
  - `community_id` 列的数据类型（建议 `long` 或 `int`）
  - 文件路径和格式（JSON Lines，UTF-8）
- **协作讨论**：
  - 检索时 PageRank 分数怎么用？是直接做排序权重，还是和向量相似度做加权融合？
  - 社区信息怎么用？是命中一个实体后召回同社区其他实体，还是用社区ID做过滤？

### 5.3 协作成员D（实验评估与项目统筹）

- **他依赖你**：Scalability 实验的原始数据和图表
- **你需要给他**：
  - 完整的实验数据表格（CSV 格式，含每组实验的时间、数据量、配置参数）
  - 高清图表文件（PNG/SVG）
  - 一段文字描述：算法运行效率、扩展性结论、遇到的瓶颈

---

## 六、技术实现建议

### 6.1 推荐的技术路径

```
vertices.jsonl + edges.jsonl
        ↓
  Spark DataFrame (PySpark)
        ↓
  GraphFrame(v, e) 或 GraphX
        ↓
  ├─→ PageRank (内置API，直接调用)
  └─→ Louvain (需额外处理：推荐 NetworkX 方案)
        ↓
  vertices_enriched.jsonl (添加 pagerank, community_id)
        ↓
  Scalability 实验 + 可视化
```

### 6.2 关键 Spark API 速查

```python
from graphframes import GraphFrame

# 加载数据
v = spark.read.json("output_jsonl/vertices.jsonl")
e = spark.read.json("output_jsonl/edges.jsonl")

# 构造图
g = GraphFrame(v, e)

# PageRank
results = g.pageRank(resetProbability=0.15, maxIter=10)
vertices_with_pr = results.vertices  # 多了 pagerank 列

# 连通分量（Louvain 的简化替代）
sc.setCheckpointDir("/tmp/checkpoints")  # 必须设置
cc = g.connectedComponents()
```

### 6.3 Louvain 的 NetworkX 备选方案

如果 Spark GraphFrames 没有 Louvain，可以：

```python
import networkx as nx

# 将 edges DataFrame 转为 NetworkX 图
G = nx.from_pandas_edgelist(edges_df, 'src', 'dst')

# Louvain 社区发现
communities = nx.community.louvain_communities(G, seed=42)
# 或：partition = nx.community.louvain_communities(G)

# 将结果映射回 DataFrame
```

> 注意：NetworkX 是单机内存计算，15万节点/11万边的图完全可以容纳。如果后续数据量扩展到百万级，再考虑纯 Spark 方案。

---

## 七、常见问题与应对

### Q1：PageRank 跑完后，分数最高的节点看起来是噪声？
- 可能原因：某些抽取边（`source=extracted`）质量差，导致一个冷门实体被大量错误指向
- 应对：分别对 `seed` 边和 `extracted` 边跑 PageRank，对比差异；或给 `extracted` 边更低的权重

### Q2：Louvain 社区太大（一个社区占了80%节点）？
- 可能原因：图的整体连通性太高，存在一个巨大的连通分量
- 应对：尝试调整 Louvain 的 resolution 参数（更高的 resolution 会产生更多小社区）；或先用弱连通分量预分割

### Q3：Spark 跑图算法时内存溢出？
- 可能原因：分区数太少，单个分区数据量过大
- 应对：增加 `spark.sql.shuffle.partitions`；对 edges 做 `repartition(200)`；或增加 executor 内存

### Q4：成员A的图数据格式变了怎么办？
- 应对：和成员A约定好固定的 Schema 接口（字段名、类型、是否可空），任何变更提前同步

---

## 八、时间规划建议

结合项目整体时间线（共6周），你的重点工作时间：

| 周次 | 你的重点 |
|------|---------|
| Week 1-2 | 环境搭建（Spark + GraphFrames），加载数据，跑通 PageRank 基础版 |
| Week 3 | 实现 Louvain 社区发现，整合结果到 enriched 节点表 |
| Week 4 | 与成员C对接，确认 enriched 数据格式；开始设计 Scalability 实验 |
| Week 5 | 跑完所有 Scalability 实验，生成图表 |
| Week 6 | 整理实验结果，撰写报告章节，配合成员D做PPT |

---

## 九、总结：你工作的价值

| 如果没有你的工作 | 有了你的工作 |
|----------------|-------------|
| 图谱只是 flat 的节点和边列表，检索时随机采样 | 节点有了重要性排序，检索优先关注核心实体 |
| 检索只能做单点匹配，无法利用语义关联 | 社区发现让语义相关的实体聚类，支持"邻居召回" |
| 系统性能未知，无法声称"Scalable" | 有实验数据证明算法随数据增长的可扩展性 |

**一句话**：你让知识图谱从"一堆数据"变成了"有结构、有权重、有智能"的检索增强引擎。
