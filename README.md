# 基于知识图谱的人工智能专业培养方案智能问答系统

本项目面向人工智能专业学生在培养方案查询和课程规划中的实际需求，设计并实现了一套基于 Graph RAG 的智能问答原型系统。当前以 2023 级培养方案为数据基础，验证自然语言查询、课程关系检索、培养路径分析及证据溯源等功能，为后续扩展至更多年级和实际教学服务场景提供基础。

> 当前知识库只对应 **2023级人工智能专业**。不同年级的培养方案可能不同，系统不会把当前数据泛化为其他年级的正式选课规则。

## 项目解决什么问题

培养方案信息密集、表格较多，新生和低年级学生常见的问题包括：

- “知识工程是多少学分，建议什么时候修？”
- “第四学期有哪些专业核心课？”
- “第六学期有哪些专业选修课？”
- “人工智能专业有哪些毕业要求？”

本项目采用 Graph RAG 路线：先将培养方案组织为实体与关系，再进行实体链接和图邻域检索，最后把检索证据组织成答案。回答同时标注适用范围与来源，便于学生核对，也便于答辩展示系统如何降低幻觉。

## 当前完成度

- 知识图谱构建：6 类实体、6 类关系，当前数据含 70 个实体和 170 条关系；构建前校验实体类型、关系方向、端点和资料来源。
- 图检索：提供基础/增强两种策略；增强策略支持别名、意图识别、关系过滤和多条件交集查询。
- 问答：网页可在离线证据回答与 DeepSeek Graph RAG 之间切换；LLM答案要求引用 `[E1]` 形式的图谱证据。
- 产品界面：提供 Streamlit 学生端网页，展示答案、培养路径、课程关系图、适用范围、来源和图谱证据。
- 数据质量：构建前执行 Schema、重复实体、悬空关系和类型校验。
- 可验证性：包含 12 项单元测试与基础/增强检索对比评测。

## 系统结构

```text
培养方案 PDF
    ↓ 人工核对 / LLM 抽取
结构化实体与关系
    ↓ Schema 校验
Neo4j 图数据库 ────── 内存图（离线演示）
    ↓                      ↓
实体链接 → 意图识别 → 1 跳邻域检索 → 关系过滤/多条件筛选
    ↓
离线答案 / DeepSeek 生成
    ↓
学生端网页：答案 + 版本范围 + 来源 + 图谱证据
```

更详细的设计见 [系统架构](docs/architecture.md)。

## 知识图谱 Schema

| 类型 | 内容 |
| --- | --- |
| 实体 | Program、Course、CourseCategory、Semester、Department、GraduationRequirement |
| 关系 | HAS_COURSE、HAS_REQUIREMENT、BELONGS_TO_CATEGORY、OFFERED_IN、TAUGHT_BY、SUPPORTS_REQUIREMENT |

课程节点还保存课程代码、学分、总学时、是否必修等属性。`SUPPORTS_REQUIREMENT` 已保留在 Schema 中，但在没有可靠课程—毕业要求映射依据前不写入数据，避免编造关系。

## 快速体验（无需 Neo4j 和 API Key）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/inspect_data.py
python scripts/offline_demo.py
python scripts/evaluate_retrieval.py
streamlit run app.py
```

打开终端显示的本地网址，即可使用学生端问答页面。

## DeepSeek Graph RAG 模式

网页的 DeepSeek 模式可以直接使用内存图完成 Graph RAG，不强制要求 Neo4j。复制配置模板并填写 API Key：

```bash
cp .env.example .env
```

```dotenv
DEEPSEEK_API_KEY=你的密钥
ANSWER_MODE=llm
RETRIEVAL_STRATEGY=enhanced
```

随后运行 `streamlit run app.py`，侧栏会出现“DeepSeek Graph RAG”。如果需要演示 Neo4j 图存储，再启动 Neo4j：

```bash
docker compose up -d neo4j
```

构建 Neo4j 图谱并在命令行提问：

```bash
python scripts/build_kg.py
python scripts/query.py "知识工程是多少学分，建议在哪个学期修读？"
```

设置 `EXTRACTION_MODE=llm` 后可使用 DeepSeek 从文本语料抽取实体和关系；默认 `structured` 模式使用人工核对后的结构化数据，更适合稳定答辩。

## 常用命令

| 命令 | 用途 | 外部依赖 |
| --- | --- | --- |
| `make inspect` | 校验知识库规模与 Schema | 无 |
| `make offline-demo` | 显示实体链接和图谱证据 | 无 |
| `make evaluate` | 运行检索评测 | 无 |
| `make test` | 运行单元测试 | 无 |
| `make app` | 启动学生端网页 | 无 |
| `make build` | 将结构化数据写入 Neo4j | Neo4j |
| `make demo` | Neo4j + DeepSeek 完整问答 | Neo4j、API Key |

当前 5 题小型评测用于验证代码回归，而不是通用性能结论。现有结果为：基础策略实体链接 40%、证据检索 60%；增强策略两项均为 100%。最终答辩前需要扩充评测规模。

## 数据与来源

- 原始依据：天津大学《2023级人工智能专业培养方案》。
- 结构化知识库：`data/raw/curriculum_structured.json`。
- 文本抽取语料：`data/raw/curriculum_docs.txt`。
- 评测集：`data/evaluation/questions.json`。

目前录入的是适合 MVP 演示的代表性课程，而不是教务系统的完整替代品。课程先修关系没有出现在现有依据中，因此系统不回答或推断先修课。

## 项目文档

- [系统架构说明](docs/architecture.md)
- [数据字典](docs/data_dictionary.md)
- [期中答辩方案](docs/midterm_defense.md)
- [最终答辩提纲](docs/report_outline.md)

## 安全

`.env` 已被 Git 忽略。不要提交 DeepSeek API Key、Neo4j 密码或其他个人凭据。
