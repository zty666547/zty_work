# DebugPath 最终答辩事实清单

本文档是最终答辩和展示页面的统一内容依据。只记录当前仓库能够通过代码、轨迹或评测文件复现的事实。

## 一句话成果

DebugPath 将一次性 Graph RAG 扩展为可回放的主动诊断闭环：系统先检索候选原因，再选择问题效用最高的下一问，依据用户观察更新原因概率和候选子图，最终沿图谱生成检查、修复、风险与来源链。

## 图谱构建

- 基础因果图谱与证据层：132个节点、345条关系；
- 最终演示使用的服务感知图谱：147个节点、378条关系；
- 最终图谱共有15类节点、27类受控关系和33条`EvidenceChunk`；
- 15类节点按职责分为故障与证据、交互推理、环境约束、方案输出四层。

三种关键关系不能混用：

- `HAS_POSSIBLE_CAUSE`只定义候选原因；
- `CHUNK_SUPPORTS_CAUSE`将检索证据映射到原因，用于初始排序；
- `OBSERVATION_SUPPORTS`保存条件概率，用户回答后真正参与贝叶斯更新。

事实来源：`docs/graph-explanation.md`、`src/graph/schema_v2.py`、`data/demo/open_webui_ollama_trajectory.json`。

## 检索与推理优化

初始检索将固定错误特征、BM25证据得分和图谱先验结合，形成候选原因概率。主动选问使用：

```text
IG(q) = H(C) - E[H(C | answer)]
预计信息收益 = IG(q) × 可回答率
问题效用 = 预计信息收益 - 检查成本惩罚 - 风险惩罚
```

用户回答后，系统读取`OBSERVATION_SUPPORTS`中的条件概率，对全部候选原因执行贝叶斯更新。回答“不清楚”时记录轨迹，但不更新原因概率，也不增加有效回答数。

停止需要同时满足：

- 最高候选概率不低于78%；
- 第一名相对第二名至少领先20%；
- 至少获得两个有效回答。

系统还会在达到最大追问轮数、没有剩余问题或剩余问题信息增益过低时停止，并明确标记证据是否充分。

事实来源：`docs/v2-information-gain.md`、`src/diagnosis/planner_v2.py`、`src/diagnosis/engine_v2.py`。

## 固定演示轨迹

演示案例：Open WebUI容器无法连接宿主机Ollama。

### 第0轮：初始检索

- 服务地址配置错误：56.0%；
- 必需环境变量缺失：13.8%；
- 目标服务未启动：13.8%；
- 端口被其他进程占用：8.3%；
- 认证信息无效：8.3%；
- 当前熵：1.850 bit；
- 下一问的信息增益：0.733 bit；
- 预计可回答率：90%；
- 问题效用：0.640。

下一问：宿主机访问Ollama正常，但Open WebUI容器使用当前地址访问失败吗？

### 第1轮：回答“是”

- 新增观察：宿主机成功、容器失败；
- 服务地址配置错误升至95.2%；
- 当前熵降至0.364 bit；
- 下一问：检查当前进程后，必需的环境变量是否为空或不存在？

### 第2轮：回答“否”

- 服务地址配置错误升至96.9%；
- 当前熵降至0.250 bit；
- 满足置信度、领先差距和有效证据数停止条件。

事实来源：`data/demo/open_webui_ollama_trajectory.json`。使用`python scripts/export_v2_demo.py`可重新生成。

## 最终方案与知识注入

固定案例的最终证据链为：

```text
服务地址配置错误
  → Open WebUI容器访问宿主机Ollama
  → Ollama /api/tags
  → 从容器检查目标端点
  → 配置OLLAMA_BASE_URL
  → 修改前保留原值
  → Docker、Open WebUI和Ollama官方文档
```

程序先把图谱结果转换为声明与证据白名单，再允许DeepSeek调整顺序和表达侧重。模型不能新增原因、命令、修复或来源。

当前边界测试结果：

- 9条合法编排全部接受；
- 24条非法编排全部拒绝；
- 该结果只验证程序化结构边界，不等于开放式大模型安全性。

事实来源：`data/evaluation/injection_results.json`、`src/diagnosis/generator.py`。

## 算法实验结论

- 42条确认案例均已被开发者查看；
- 可回答性感知策略改变了其中15条案例的首问；
- 在原28条开发案例中，纯信息增益Top-1为96.4%，完整策略为100%；
- 这些结果只能说明算法修改确实影响选问行为，不能作为第二版无偏测试成绩。

首次14条冻结测试在模型封存后只执行一次：

- 不追问Top-1为50.0%；
- 固定顺序为64.3%；
- 随机追问为60.4%；
- 纯信息增益为64.3%；
- 完整策略为64.3%；
- 其中5条在故障族入口失败，并按端到端失败计入。

这14条案例已经被查看并用于第二版开发反馈，不能再次充当新的无偏测试集。

事实来源：`data/evaluation/v2_strategy_development_results.json`、`data/evaluation/frozen_test_results.json`、`docs/frozen-evaluation-analysis.md`。

## 工程验证

- 当前自动化测试：73项通过；
- 14个候选原因均有观察、检查、修复和直接来源；
- 当前公开案例池：28条开发案例、14条已执行冻结测试案例、3条未确认案例。

复现命令：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_v2_demo.py
.venv/bin/python scripts/evaluate_v2_strategy.py
.venv/bin/python scripts/evaluate_injection.py
.venv/bin/python scripts/audit_second_stage.py
.venv/bin/python scripts/audit_real_case_split.py
.venv/bin/python scripts/audit_final_defense.py
```

## 答辩中不能扩大的结论

- 不能说第二版在真实环境中的准确率达到100%；
- 不能说成本项和风险项已经得到充分实验验证；
- 不能说DeepSeek决定了根因或自由生成修复方案；
- 不能说动态图谱每轮重新构建了底层知识库；
- 不能将147个节点本身表述为项目创新。

最终汇报应把贡献概括为：图谱结构可解释、问题选择经过优化、诊断轨迹能够回放、最终答案具有完整证据链。
