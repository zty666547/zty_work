# DebugPath：交互式故障诊断 Graph RAG

DebugPath 面向信息不完整的 AI 开发环境报错。

普通 RAG 根据用户第一次输入直接回答；DebugPath 会从知识图谱中找到候选原因，主动选择最有价值的问题，并根据用户回答逐轮更新判断，最终给出带检查步骤、风险提示和来源的排查方案。

**在线演示：** [打开 DebugPath](https://ztywork-w4dzhwedqtyxgzbuqzkyus.streamlit.app/)

## 整体流程

```text
用户报错
  ↓
检索相关证据和候选原因
  ↓
选择信息量最大的问题
  ↓
用户回答，更新原因概率
  ↓
继续追问或定位目标原因
  ↓
生成检查、修复、风险和来源
```

图谱本身保持不变，每轮更新候选原因概率和下一问。候选节点保留，概率降低不等于排除。

## 核心内容

### 1. 知识图谱

图谱包含故障、原因、问题、观察、检查、修复、风险和来源。当前图谱有 **130 个节点、338 条关系**。

### 2. 动态检索

系统先用 BM25 检索相关证据，再结合图谱得到候选原因。每轮通过信息增益选择下一问，并根据用户回答更新原因概率，直到满足停止条件。

### 3. 安全生成

排查方案必须包含前置检查、风险等级和来源。DeepSeek 只负责组织已经验证的内容，不能自由添加原因、命令或证据；验证失败时自动使用离线答案。

## 当前范围

系统覆盖三个故障族：

- Python 模块导入错误
- PyTorch GPU 与 CUDA 问题
- API 与 Neo4j 连接配置问题

页面可展示检索证据、候选原因概率、问题选择理由、诊断子图和最终排查方案。

“诊断轨迹”页支持逐轮回看问题、用户反馈、排名和概率变化，以及停止原因。可下载轨迹 JSON，或截取初始、中间、结束三个阶段用于答辩展示。

## 快速运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

答辩时可直接打开上方公网地址。部署步骤和 Windows/macOS 本地备用入口见[答辩部署说明](docs/deployment.md)。

可以直接测试：

```text
ModuleNotFoundError: No module named 'pandas'
torch.cuda.is_available() 返回 False
Neo4j Connection refused
API 请求返回 401 Unauthorized
```

离线演示不需要 API 或 Neo4j：

```bash
python scripts/offline_demo.py
```

运行全部测试和评测：

```bash
pytest -q
python scripts/evaluate_diagnosis.py
python scripts/evaluate_ablation.py
python scripts/evaluate_injection.py
```

## 当前结果

30 条来源约束的合成诊断路径上：

| 方法 | Top-1 | 平均追问 |
| --- | ---: | ---: |
| 不追问 | 73.3% | 0.00 |
| 固定顺序 | 96.7% | 3.23 |
| 随机追问 | 97.5% | 3.23 |
| 信息增益 | 100.0% | 2.80 |

以上结果用于验证系统机制，不能代表真实环境中的准确率。详细设置见[评测说明](docs/evaluation.md)。

## 答辩展示

- [5分钟网页幻灯片](presentation/index.html)：方向键翻页，按 `P` 进入演讲者模式，按 `B` 切换静态模式。
- [完整展示大纲](presentation/大纲-v2.md)
- [5分钟答辩演讲稿](presentation/5分钟演讲稿.md)
- [小组答辩速查手册](docs/team-defense-guide.md)：项目现状、代码结构、实验边界和针对性问答。

## 代码结构

| 位置 | 功能 |
| --- | --- |
| `src/graph/` | 图谱结构、构建和 Neo4j 写入 |
| `src/retrieval/` | BM25 证据检索与候选原因融合 |
| `src/diagnosis/` | 主动询问、概率更新、计划验证和答案生成 |
| `data/raw/` | 图谱与证据数据 |
| `data/evaluation/` | 诊断案例与实验结果 |
| `app.py` | Streamlit 演示页面 |

## 可选配置

需要 DeepSeek 或 Neo4j 时，复制配置模板并只在本地填写：

```bash
cp .env.example .env
```

Neo4j 构建与演示方法见[Neo4j 演示](docs/neo4j_demo.md)。

## 项目边界

- 当前只有三个故障族和 30 条证据片段。
- 概率参数尚未通过大规模真实案例校准。
- 系统只展示检查命令，不会自动执行。
- 知识库外的问题会明确拒绝，不让大模型自由补全。

更多内容见[系统架构](docs/architecture.md)、[数据字典](docs/data_dictionary.md)、[答辩方案](docs/midterm_defense.md)和[修改记录](CHANGELOG.md)。培养方案旧版本保留在 `archive/curriculum-graphrag-v1` 分支和同名标签中。
