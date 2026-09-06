# DebugPath：交互式 AI 开发环境故障诊断 Graph RAG

DebugPath 面向信息不完整的开发环境报错，不直接让大模型猜答案。系统从因果知识图谱中召回候选原因，选择期望信息增益最高的问题主动追问，随后更新原因概率，并生成经过前置条件、风险和来源校验的排查方案。

项目当前聚焦一个研究问题：

> 相比“一次提问、一次回答”的普通 RAG，图谱驱动的有限轮主动询问能否更快缩小故障原因集合，并减少无依据或高风险的修复建议？

## 当前实现

- `causal_graph`：把故障、原因、观察、问题、检查、修复、平台、版本条件、风险和来源组织成受控图谱；
- `evidence_retrieval`：使用离线BM25从证据片段召回相关内容，并将文本分数与图谱先验融合；
- `active_diagnosis`：维护候选原因概率，通过期望信息增益选择下一问，并根据用户观察执行贝叶斯更新；
- `verified_plan`：修复动作必须具有前置检查、风险等级和来源，危险命令或高风险动作会被阻止；
- `offline`：完全不依赖 Neo4j 和 API，保证现场演示稳定；
- `deepseek`：大模型只选择白名单声明、证据和展示侧重点，技术内容仍由已验证模板输出。

当前覆盖三个故障族：Python 模块导入、PyTorch GPU/CUDA、API 与 Neo4j 连接配置。合并知识库包含 **130个节点、338条关系、30个EvidenceChunk、14个候选原因和14个主动问题**。

## 当前架构

```text
错误描述 ─→ BM25证据片段 ─→ 场景识别与图谱候选原因
                              │
                       文本分数＋图谱先验
                              │
                              ↓
                    计算问题期望信息增益
                              │
                   ┌──────────┴──────────┐
                   ↓                     │
                主动追问 → 用户观察 → 概率更新
                   │                     │
                   └──── 未满足停止条件 ─┘
                              ↓
                  检查 → 修复 → 风险 → 来源
                              ↓
                  规则验证 → 离线模板/LLM受控编排
```

选问目标为：

```text
Utility(q) = ExpectedInformationGain(q) - CheckCost(q) - RiskCost(q)
```

达到置信阈值、最大追问轮数、没有剩余问题或信息增益不足时停止。

## 主要代码

```text
src/diagnosis/
  engine.py            场景识别、信息增益、贝叶斯更新和停止策略
  policies.py          直接、固定、随机和信息增益四种选问策略
  planner.py           检查—修复计划与安全验证
  service.py           Web、CLI和评测共用入口
  generator.py         声明—证据白名单与确定性答案渲染
src/graph/
  schema.py            实体、关系及方向约束
  artifact.py          确定性排序、统计与内容指纹
  builder.py           DebugPath子图写入Neo4j
src/retrieval/
  bm25.py              中英文分词、BM25召回与图文分数融合
data/raw/
  debugpath_knowledge.json       受控因果知识图谱
  debugpath_evidence.json        30条可追溯文本证据片段
data/evaluation/
  diagnosis_cases.json           冻结诊断路径
  sources.json                   案例来源登记表
  baseline_results.json          可复现的策略对比结果
  ablation_results.json          图谱、文本、主动询问消融结果
  injection_results.json         声明—证据白名单攻防结果
app.py                 Streamlit交互页面
```

详细设计见[系统架构](docs/architecture.md)、[数据字典](docs/data_dictionary.md)和[证据来源](docs/evidence_sources.md)。

## 1. 安装与离线运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/inspect_data.py
python scripts/prepare_graph.py
python scripts/offline_demo.py
python scripts/evaluate_diagnosis.py
python scripts/evaluate_ablation.py
python scripts/evaluate_injection.py
pytest -q
```

离线模式不需要数据库或密钥。

## 2. Web 演示

```bash
streamlit run app.py
```

可直接输入：

```text
ModuleNotFoundError: No module named 'pandas'
torch.cuda.is_available() 返回 False
Neo4j Connection refused
API 请求返回 401 Unauthorized
```

页面会展示BM25召回证据、融合后的候选概率、下一问的选择理由、诊断子图和最终排查方案。

## 3. DeepSeek 与 Neo4j

复制配置模板，并只在本地填写密钥：

```bash
cp .env.example .env
```

配置 `DEEPSEEK_API_KEY` 后，页面可以切换到DeepSeek受控编排模式。模型只能返回完整的`C1/C2/C3`声明顺序、已召回的`E001…`证据ID和有限的展示侧重点；原因、检查命令、修复动作、风险与来源均由程序从已验证计划中渲染。需要展示持久化图谱时：

```bash
python scripts/prepare_graph.py
docker compose up -d neo4j
python scripts/build_kg.py
python scripts/check_neo4j.py
```

`prepare_graph.py`会生成可重建、不入库的`data/processed/debugpath_graph.json`，其中记录稳定排序后的节点、关系、分类型统计和SHA-256内容指纹。构建脚本只更新带`project=DebugPath`标记的节点，不清空数据库中的其他图谱；检查脚本会只读核对本地与数据库中的节点、关系、标签和关系类型。可直接用于答辩的查询见[Neo4j演示](docs/neo4j_demo.md)。

## 4. 评测

```bash
python scripts/evaluate_diagnosis.py
```

四种策略使用完全相同的图谱、案例、概率更新和停止条件；随机策略固定种子并重复 100 次：

| 选问策略 | Top-1 | MRR | 平均追问 | 3问内成功 |
| --- | ---: | ---: | ---: | ---: |
| 不追问 | 73.3% | 0.861 | 0.00 | 73.3% |
| 固定顺序 | 96.7% | 0.983 | 3.23 | 46.7% |
| 随机追问 | 97.5% | 0.988 | 3.23 | 49.1% |
| **信息增益** | **100.0%** | **1.000** | **2.80** | **66.7%** |

当前评测集包含三个故障族各10条、覆盖全部14个原因的30条来源约束合成路径，其中9条开发集、21条冻结测试集。四种选问策略现在共享BM25证据检索和图谱先验融合；测试集上信息增益策略Top-1为100%，固定顺序为95.2%，随机追问平均为96.5%，不追问为71.4%。合成路径仍不能代表真实世界泛化能力。评测设计、指标解释与限制见[对比实验](docs/evaluation.md)。

消融实验进一步拆分了各组件贡献：仅图谱先验Top-1为23.3%，仅文本证据为76.7%，当前简单图文融合为73.3%；加入主动询问后，图谱主动诊断与混合主动诊断均为100%，而混合方案把平均追问从3.10次降到2.80次。这里没有隐藏“仅文本初始排序略高于简单融合”的结果，它说明当前人工图谱先验和固定融合权重仍需校准，而不是说明图谱无用。

知识注入验证覆盖三个故障族的9次合法编排，以及未知声明、遗漏声明、重复声明、未召回证据、重复证据、非法侧重点、自由文本和畸形类型共24次攻击。当前合法接受率100%，非法拒绝率100%。这些是针对结构化白名单边界的确定性机制测试，不代表对任意提示注入攻击的通用防御能力。

## 5. 项目边界

- 概率参数是可解释启发式值，尚未通过大规模真实案例校准；
- 当前只覆盖三个故障族，不是通用运维系统；
- 系统只展示检查命令，不自动执行；
- 官方文档能支持检查和兼容原则，不能直接证明某个用户故障的真实根因；
- 当前知识库外的问题会明确拒绝，不交给大模型自由补全。
- 当前BM25语料只有30条证据片段，文本分数与图谱先验的融合权重仍是启发式参数；

培养方案 Graph RAG 旧版本完整保留在 `archive/curriculum-graphrag-v1` 分支和同名标签中。期中答辩说明见[答辩方案](docs/midterm_defense.md)，每次阶段修改记录见[CHANGELOG](CHANGELOG.md)。
