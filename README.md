<h1 align="center">基于知识图谱的 RAG 系统构建</h1>

<p align="center">
  知识工程实践任务 · 电影领域知识图谱 · Graph RAG 问答
</p>

<p align="center">
  <b>Neo4j</b> · <b>Python</b> · <b>DeepSeek API</b>
</p>

---

## 📌 项目简介

本项目实现一个 **基于知识图谱的 RAG（Graph RAG）问答系统**。与传统的「向量数据库 RAG」不同，它把领域知识组织成**知识图谱**（实体 + 关系），查询时先在图上做**结构化检索**（实体链接 + 邻域扩展），再把检索到的**子图**作为上下文交给大模型生成回答。

相比纯向量检索，Graph RAG 的优势在于：

- ✅ 能建模并回答**多跳关系**问题（如「诺兰的演员还演过哪些电影？」）
- ✅ 检索结果**结构化、可解释**，方便答辩展示
- ✅ 借助图谱约束，显著**降低幻觉**

内置一套**电影领域示例数据**（Person / Movie / Genre 三类实体），开箱即用、可直接演示。

---

## 🏗️ 系统架构

```
数据层(data/)                    抽取层(src/extraction/)
├─ movies_structured.json   →   ├─ LLMClient（DeepSeek 封装）
└─ movie_docs.txt               └─ EntityRelationExtractor（文本→三元组）
        │                                   │
        └────────────┬──────────────────────┘
                     ▼
        图谱层(src/graph/)  ──►  Neo4j 图数据库(7687 Bolt)
        ├─ Neo4jClient（连接/Cypher）
        └─ GraphBuilder（MERGE 写入/建索引）
                     │
                     ▼
        检索层(src/rag/)
        ├─ GraphRetriever（实体链接→邻域扩展→子图上下文）
        └─ GraphRAGChain（检索 + Prompt + LLM 生成）
                     │
                     ▼
              用户问题 → 最终回答 + 可解释上下文
```

详细说明见 [docs/architecture.md](docs/architecture.md)。

---

## ✨ 功能特性

- **两种图谱构建模式**：
  - `structured`：直接读取整理好的三元组建图（确定性、无需 LLM）
  - `llm`：让 DeepSeek 从自然语言文本**自动抽取**实体与关系（展示 LLM 信息抽取能力）
- **Graph RAG 检索**：实体链接 → 邻域扩展（N 跳）→ 子图上下文组装
- **防幻觉**：仅允许基于图谱上下文回答，无相关上下文则明确拒答
- **多形态使用**：CLI 问答、一键 Demo、Jupyter Notebook
- **可维护**：模块解耦、集中配置、离线单元测试

---

## 📁 目录结构

```
kg-rag-system/
├── config/settings.py          # 全局配置（读取 .env）
├── data/
│   ├── raw/                    # 输入数据（结构化 JSON + 文本语料）
│   ├── processed/              # 抽取/处理产物（gitignore）
│   └── kg/                     # 图谱导出/Neo4j 数据卷
├── src/
│   ├── data/loader.py          # 数据加载
│   ├── extraction/             # llm_client + extractor（信息抽取）
│   ├── graph/                  # neo4j_client + builder（图谱构建）
│   ├── rag/                    # retriever + chain + prompts（检索生成）
│   └── utils/logger.py         # 日志
├── scripts/                    # build_kg / query / run_demo
├── notebooks/demo.ipynb        # 答辩演示 Notebook
├── tests/                      # 离线单元测试
├── docs/                       # architecture.md + report_outline.md（报告提纲）
├── docker-compose.yml          # Neo4j 容器编排
├── Makefile                    # 一键命令
├── requirements.txt
└── .env.example                # 环境变量模板
```

---

## 🚀 快速开始

### 0. 前置条件

- Python ≥ 3.9
- Neo4j 5.x（**本机直接安装** 或 **Docker**，见下方「启动 Neo4j」）
- DeepSeek API Key（[申请地址](https://platform.deepseek.com)）

### 1. 环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 与 Neo4j 密码
```

### 2. 启动 Neo4j

**方式 A：Docker（推荐，一条命令）**
```bash
docker compose up -d neo4j
# 浏览器控制台：http://localhost:7474  用户名 neo4j / 密码 12345678
```

**方式 B：本机安装**
从 [Neo4j 官网](https://neo4j.com/download-center/) 下载，启动后设置密码为 `12345678`（或同步到 `.env`）。

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 构建知识图谱

```bash
make build          # 结构化模式（无需 LLM，最稳）
# 或
make build-llm      # 用 DeepSeek 从文本抽取再建图
```

### 5. 问答

```bash
make query          # 内置示例问题
# 或自定义
python scripts/query.py "诺兰导演了哪些电影？"
```

### 6. 一键演示 / 测试

```bash
make demo           # 建图 + 示例问答（适合答辩现场）
make test           # 离线单元测试
```

---

## 🧪 演示问题（可在答辩时使用）

| 问题 | 覆盖能力 |
| --- | --- |
| 克里斯托弗·诺兰导演了哪些电影？ | 单实体关系查询 |
| 莱昂纳多·迪卡普里奥参演过哪些电影？ | 实体关系查询 |
| 肖申克的救赎是什么类型的电影？ | 属性/关系查询 |

> 在 `http://localhost:7474` 执行 `MATCH (n:Entity) RETURN n LIMIT 25` 可看到图谱可视化。

---

## 🔧 GitHub 仓库创建与推送

**第一步：在 GitHub 手动创建空仓库**

到 <https://github.com/new>：
- Repository name：`kg-rag-system`
- 建议选 **Public**（答辩/作品集展示），不要勾选「Add README / .gitignore / license」（避免冲突）
- 点击 **Create repository**

**第二步：进入项目目录后初始化并推送**

> 先在终端 `cd` 到本项目的根目录（即本 README 所在的 `kg-rag-system/` 目录），再执行：

```bash
# 初始化仓库
git init

# 把所有文件加入暂存区（.gitignore 会过滤 .env 与密钥等敏感文件）
git add .
git status          # 确认没有把 .env 加进去！

# 首次提交（可使用 GitHub 提示的账号邮箱）
git commit -m "feat: 基于知识图谱的 RAG 系统（Graph RAG）初始化
- 电影领域示例数据与两个抽取模式
- Neo4j 图谱构建 + Graph RAG 检索问答链路
- CLI / Notebook / Makefile 一键运行
- 架构文档与答辩报告提纲"

# 关联远端仓库（把 URL 替换成你的仓库地址）
git remote add origin https://github.com/<你的用户名>/kg-rag-system.git

# 默认分支命名为 main 并推送
git branch -M main
git push -u origin main
```

**第三步：验证**

刷新 GitHub 页面即可看到仓库内容。记得**确保 `.env` 没有被提交**（`.gitignore` 已处理；若误提交请立即删除并更换 API Key）。

---

## 🛡️ 安全提示

- `.env` 含 DeepSeek Key 与 Neo4j 密码，**已被 `.gitignore` 排除**，切勿手动强制提交。
- 演示前建议在 Neo4j 中用 `MATCH (n) DETACH DELETE n` 清空，再用 `make build` 重建，确保数据干净。

---

## 📚 文档

- [系统架构说明](docs/architecture.md)
- [期末答辩报告提纲](docs/report_outline.md)

## 📄 许可证

本项目用于学习与课程实践。
