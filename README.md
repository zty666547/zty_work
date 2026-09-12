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

图谱包含故障、原因、问题、观察、检查、修复、风险和来源。当前图谱有 **132 个节点、345 条关系**。

### 2. 动态检索

系统先用 BM25 检索相关证据，再结合图谱得到候选原因。每轮综合信息增益、用户可回答率、检查成本和风险选择下一问，并根据用户回答更新原因概率，直到满足停止条件。

### 3. 安全生成

排查方案必须包含前置检查、风险等级和来源。DeepSeek 只负责组织已经验证的内容，不能自由添加原因、命令或证据；验证失败时自动使用离线答案。

## 当前范围

系统覆盖三个故障族：

- Python 模块导入错误
- PyTorch GPU 与 CUDA 问题
- API 与 Neo4j 连接配置问题

页面可展示检索证据、候选原因概率、问题选择理由、诊断子图和最终排查方案。

“诊断轨迹”页支持逐轮回看问题、用户反馈、排名和概率变化，以及停止原因。可下载轨迹 JSON，或截取初始、中间、结束三个阶段用于答辩展示。

诊断结束后可回填实际根因并下载脱敏案例 JSON。未经过检查或修复确认的记录会自动标为“未确认”，不能计入准确率；案例只在浏览器中生成，不会自动上传。

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
python scripts/evaluate_active_algorithm.py
python scripts/evaluate_public_cases.py
python scripts/evaluate_ablation.py
python scripts/evaluate_injection.py
python scripts/evaluate_frozen_test.py
```

## 当前结果

30 条来源约束的合成诊断路径上：

| 方法 | Top-1 | 平均追问 |
| --- | ---: | ---: |
| 不追问 | 73.3% | 0.00 |
| 固定顺序 | 96.7% | 3.43 |
| 随机追问 | 97.4% | 3.32 |
| 可回答性感知信息增益 | 100.0% | 2.83 |

以上结果用于验证系统机制，不能代表真实环境中的准确率。详细设置见[评测说明](docs/evaluation.md)。

首次14条未见案例冻结测试中，不追问、固定顺序、随机追问、纯信息增益和完整策略的端到端Top-1分别为50.0%、64.3%、60.4%、64.3%和64.3%。其中5条在故障族识别入口失败；纯信息增益与完整策略表现相同。该结果用于暴露下一版研究问题，不能表述为真实世界总体准确率。详见[冻结测试分析](docs/frozen-evaluation-analysis.md)。

第二版正在开发可解释的故障族候选检索：将固定错误特征与BM25图谱证据汇总结合，并输出命中特征和证据路径。当前42条已查看案例的开发回归均能进入正确故障族，但仍需新的外部测试集验证。详见[第二版开发说明](docs/v2-development.md)。

第二版另增加一层独立服务上下文图谱。当前Open WebUI访问宿主机Ollama的案例已扩展到144个节点、366条关系，并能根据`Service`、`Endpoint`和`DeploymentContext`选择Ollama专属检查与修复。详见[服务感知图谱](docs/service-aware-graph.md)。

第二版的可回答性感知策略在42条已查看案例中改变了16条首问，开发回归Top-1高于纯信息增益；这些结果只用于解释算法行为，尚未经过新的外部测试集验证。详见[第二版信息增益分析](docs/v2-information-gain.md)。

最终阶段正在研究“可回答性感知”的主动诊断：理论上信息量很大、但普通用户难以确认的问题会被降低优先级；回答“不清楚”也不会被计作有效诊断证据。若置信度、首位领先差距或有效回答数不足，系统会明确标记“证据不足”，不把候选第一名冒充为确定结论。当前信息受限用户压力测试属于确定性模拟，尚不能替代真实用户实验。

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

第二阶段的节点、关系、概率语义与扩展约束见[因果图谱设计](docs/causal_graph_design.md)。逐原因案例缺口可通过`python scripts/audit_second_stage.py`重新生成。
