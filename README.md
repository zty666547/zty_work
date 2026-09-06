# DebugPath：交互式 AI 开发环境故障诊断 Graph RAG

DebugPath 面向信息不完整的开发环境报错，不直接让大模型猜答案。系统从因果知识图谱中召回候选原因，选择期望信息增益最高的问题主动追问，随后更新原因概率，并生成经过前置条件、风险和来源校验的排查方案。

项目当前聚焦一个研究问题：

> 相比“一次提问、一次回答”的普通 RAG，图谱驱动的有限轮主动询问能否更快缩小故障原因集合，并减少无依据或高风险的修复建议？

## 当前实现

- `causal_graph`：把故障、原因、观察、问题、检查、修复、平台、版本条件、风险和来源组织成受控图谱；
- `active_diagnosis`：维护候选原因概率，通过期望信息增益选择下一问，并根据用户观察执行贝叶斯更新；
- `verified_plan`：修复动作必须具有前置检查、风险等级和来源，危险命令或高风险动作会被阻止；
- `offline`：完全不依赖 Neo4j 和 API，保证现场演示稳定；
- `deepseek`：大模型只解释已验证的结构化计划，生成未授权命令时自动回退到离线答案。

当前覆盖三个故障族：Python 模块导入、PyTorch GPU/CUDA、API 与 Neo4j 连接配置。知识库包含 **94 个节点、218 条关系、14 个候选原因、14 个主动问题和 8 个官方来源**。

## 当前架构

```text
错误描述 ─→ 场景识别 ─→ 图谱候选原因与先验概率
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
                  规则验证 → 离线/LLM解释
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
  generator.py         离线答案与受约束LLM解释
src/graph/
  schema.py            实体、关系及方向约束
  builder.py           DebugPath子图写入Neo4j
data/raw/
  debugpath_knowledge.json       受控因果知识图谱
data/evaluation/
  diagnosis_cases.json           冻结诊断路径
  baseline_results.json          可复现的策略对比结果
app.py                 Streamlit交互页面
```

详细设计见[系统架构](docs/architecture.md)、[数据字典](docs/data_dictionary.md)和[证据来源](docs/evidence_sources.md)。

## 1. 安装与离线运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/inspect_data.py
python scripts/offline_demo.py
python scripts/evaluate_diagnosis.py
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

页面会展示候选概率、下一问的选择理由、诊断子图和最终排查方案。

## 3. DeepSeek 与 Neo4j

复制配置模板，并只在本地填写密钥：

```bash
cp .env.example .env
```

配置 `DEEPSEEK_API_KEY` 后，页面可以切换到 DeepSeek 解释模式。需要展示持久化图谱时：

```bash
docker compose up -d neo4j
python scripts/build_kg.py
python scripts/check_neo4j.py
```

构建脚本只更新带 `project=DebugPath` 标记的节点，不清空数据库中的其他图谱。

## 4. 评测

```bash
python scripts/evaluate_diagnosis.py
```

四种策略使用完全相同的图谱、案例、概率更新和停止条件；随机策略固定种子并重复 100 次：

| 选问策略 | Top-1 | MRR | 平均追问 | 3问内成功 |
| --- | ---: | ---: | ---: | ---: |
| 不追问 | 37.5% | 0.581 | 0.00 | 37.5% |
| 固定顺序 | 100.0% | 1.000 | 3.00 | 75.0% |
| 随机追问 | 100.0% | 1.000 | 3.22 | 53.2% |
| **信息增益** | **100.0%** | **1.000** | **2.75** | **75.0%** |

这组初步结果说明主动追问明显优于直接猜测，信息增益策略在保持命中的同时使用更少问题。当前只有 8 条人工构造路径，不能据此声称具备真实世界泛化能力。评测设计、指标解释与限制见[对比实验](docs/evaluation.md)。

## 5. 项目边界

- 概率参数是可解释启发式值，尚未通过大规模真实案例校准；
- 当前只覆盖三个故障族，不是通用运维系统；
- 系统只展示检查命令，不自动执行；
- 官方文档能支持检查和兼容原则，不能直接证明某个用户故障的真实根因；
- 当前知识库外的问题会明确拒绝，不交给大模型自由补全。

培养方案 Graph RAG 旧版本完整保留在 `archive/curriculum-graphrag-v1` 分支和同名标签中。期中答辩说明见[答辩方案](docs/midterm_defense.md)，每次阶段修改记录见[CHANGELOG](CHANGELOG.md)。
