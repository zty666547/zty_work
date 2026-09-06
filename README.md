# DebugPath：交互式 AI 开发环境故障诊断 Graph RAG

DebugPath 不把报错直接交给大模型猜测，而是把故障、候选原因、可观测现象、检查步骤、修复动作、风险和官方来源组织成因果知识图谱。系统维护候选原因概率，选择期望信息增益最高的下一条问题；用户补充观察结果后，系统更新概率并生成经过前置条件、风险和来源校验的排查方案。

> 当前版本是知识工程综合实践的期中原型。概率用于安排排查顺序，不代表已经确定根因；系统不会自动执行任何命令。

## 当前范围

已覆盖三个适合现场演示的故障族：

- Python `ModuleNotFoundError`、解释器错位、模块遮蔽和版本冲突；
- PyTorch CPU/CUDA构建、驱动、容器GPU映射和macOS计算后端；
- API或Neo4j的环境变量、服务地址、服务状态、端口和认证问题。

知识库当前包含 **94个节点、218条受控关系、14个候选原因、14个主动问题和8个官方文档来源**。冻结评测集包含8条完整诊断路径。

## 三层创新

1. **构建层：版本感知因果图谱。** 平台、版本条件、观察、检查、修复和来源分别建模，不把整句话当作自由关系。
2. **检索推理层：主动询问。** 使用贝叶斯更新维护候选原因，并以期望信息增益减去检查成本和风险成本来选择下一问。
3. **生成验证层：安全排查计划。** 修复动作必须有前置检查、风险等级和来源；高风险、危险命令或缺少证据的计划会被阻止。

```text
错误描述
  ↓ 场景识别
候选原因及先验概率
  ↓ 计算每个问题的期望信息增益
主动询问 → 用户观察 → 贝叶斯更新 ─┐
  ↑                                  │
  └──────── 未达到停止条件 ──────────┘
  ↓
检查前置条件 → 风险与来源验证 → 离线/DeepSeek解释
```

## 快速运行

Python 3.9及以上：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/inspect_data.py
python scripts/offline_demo.py
python scripts/evaluate_diagnosis.py
pytest -q
streamlit run app.py
```

离线模式不需要Neo4j或API密钥。网页中可以粘贴：

```text
ModuleNotFoundError: No module named 'pandas'
torch.cuda.is_available() 返回 False
Neo4j Connection refused
API 请求返回 401 Unauthorized
```

## 联网解释模式

复制配置模板并只在本地填写密钥：

```bash
cp .env.example .env
```

当 `.env` 中存在 `DEEPSEEK_API_KEY` 时，页面可启用DeepSeek解释模式。大模型只能改写已经验证的结构化计划，不能新增原因、命令或操作；调用失败时自动回退到离线答案。

## Neo4j图谱

离线诊断默认读取同一份结构化图谱。需要展示Neo4j时：

```bash
docker compose up -d neo4j
python scripts/build_kg.py
python scripts/check_neo4j.py
```

构建脚本只清理带 `project=DebugPath` 标记的节点，不会清空数据库中的其他图谱。

## 目录

```text
app.py                         Streamlit主动诊断页面
data/raw/debugpath_knowledge.json  受控因果图谱
data/evaluation/diagnosis_cases.json  冻结诊断评测集
src/diagnosis/engine.py        信息增益选问与概率更新
src/diagnosis/planner.py       排查计划与安全验证
src/diagnosis/service.py       CLI、网页和测试共用入口
src/diagnosis/generator.py     离线/LLM答案渲染
src/graph/                     Schema、内存图和Neo4j构建
scripts/                       检查、评测和演示脚本
tests/                         无外部服务的核心测试
docs/                          架构、数据字典与答辩说明
```

培养方案Graph RAG旧版本完整保留在分支 `archive/curriculum-graphrag-v1` 和同名标签中。

## 安全边界

- `.env`、真实密钥和数据库密码不会进入Git；
- 系统只展示命令，不会执行命令；
- 检查步骤先于修复动作；
- 中风险操作要求用户确认，高风险操作只提示不建议执行；
- 当前知识库外的问题会明确拒绝，不让大模型自由补全。
