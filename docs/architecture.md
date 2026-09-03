# 系统架构说明

## 1. 整体结构

本项目实现一个**基于知识图谱的 RAG（Graph RAG）问答系统**：先把数据构建成知识图谱，查询时先在图上做结构化检索，再把检索到的子图作为上下文交给大模型生成回答。

```
 ┌─────────────────────────────────────────────────────────────┐
 │                      数据层  data/                           │
 │   movies_structured.json（结构化三元组）                       │
 │   movie_docs.txt（自然语言语料，供 LLM 抽取）                  │
 └───────────────┬─────────────────────────────────────────────┘
                 │ load_input()
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                  抽取层  src/extraction/                     │
 │  EntityRelationExtractor：LLM 从文本抽取 (实体,关系,实体)      │
 │  LLMClient：DeepSeek 封装（chat / chat_json）                 │
 └───────────────┬─────────────────────────────────────────────┘
                 │ entities / relations
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                  图谱层  src/graph/                          │
 │  Neo4jClient：连接与执行 Cypher                              │
 │  GraphBuilder：MERGE 写入实体/关系，建约束与索引              │
 └───────────────┬─────────────────────────────────────────────┘
                 │ Neo4j 图数据库（7687 Bolt）
                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                  检索层  src/rag/                            │
 │  GraphRetriever：实体链接 → 邻域扩展 N 跳 → 子图上下文          │
 │  GraphRAGChain： 检索 + Prompt 组装 + LLM 生成               │
 └───────────────┬─────────────────────────────────────────────┘
                 │ 最终回答 + 可解释上下文
                 ▼
        用户问题（CLI / Notebook / API）
```

## 2. 模块职责

| 模块 | 职责 | 关键文件 |
| --- | --- | --- |
| 配置 | 统一读取 `.env` 与默认值 | `config/settings.py` |
| 数据加载 | 解析结构化数据 / 切分语料 | `src/data/loader.py` |
| 信息抽取 | 用 DeepSeek 从文本抽取三元组 | `src/extraction/extractor.py` |
| 图谱构建 | 三元组写入 Neo4j，建索引约束 | `src/graph/builder.py` |
| 图数据库 | 连接管理、Cypher 执行 | `src/graph/neo4j_client.py` |
| 检索 | 实体链接 + 邻域扩展 | `src/rag/retriever.py` |
| 生成链路 | 组装 Prompt、调用 LLM | `src/rag/chain.py` |
| Prompt | 集中管理提示模板 | `src/rag/prompts.py` |

## 3. 两种抽取模式

1. **structured**：直接读取预先整理好的三元组（`movies_structured.json`）。确定性强、无需调 LLM，适合演示与回归测试。
2. **llm**：让 DeepSeek 从自然语言 `movie_docs.txt` 抽取实体与关系，展示从非结构化文本构建知识图谱的能力。

## 4. Graph RAG 检索路径

```
问题
 └─ 1) 实体链接   link_entities()  问题字符串匹配图谱实体名
       └─ 2) 邻域扩展  expand_neighborhood()  从实体出发向外 N 跳（默认 2）
             └─ 3) 上下文组装  build_context_text()  三元组 -> 文本
                   └─ 4) 生成  DeepSeek 基于上下文回答
```

## 5. 可视化

- 浏览器：`http://localhost:7474`（Neo4j Browser），执行 `MATCH (n:Entity) RETURN n LIMIT 25`。
- 可选导出：`data/kg/` 下的 CSV / GEXF，供 networkx / Gephi 绘图。
