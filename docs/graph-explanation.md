# DebugPath图谱结构与因果逻辑

## 四层节点

DebugPath第二版共有15类节点，可按作用分成四层：

1. **故障与证据层**：`Issue`、`EvidenceChunk`、`Cause`，负责描述故障、检索官方证据并形成候选原因；
2. **交互推理层**：`DiagnosticQuestion`、`Observation`，负责把主动询问转化为可以更新原因概率的观察；
3. **环境约束层**：`Service`、`Endpoint`、`DeploymentContext`、`Package`、`Platform`、`VersionConstraint`，负责限定故障实际发生的服务、地址、部署方式、软件和版本；
4. **方案输出层**：`DiagnosticCheck`、`RepairAction`、`Risk`、`DocumentSource`，负责生成可检查、可修复、带风险且有来源的方案。

## 三种不同含义的“支持”

图中的边不能全部称为因果关系，需要区分：

- `HAS_POSSIBLE_CAUSE`表示候选集合，只说明“可能是什么”，不证明原因成立；
- `CHUNK_SUPPORTS_CAUSE`表示检索证据与原因相关，用于形成初始排序；
- `OBSERVATION_SUPPORTS`保存`P(观察结果|原因)`，用户回答后通过贝叶斯公式更新原因概率，这是动态推理真正使用的概率因果边。

因此，DebugPath中的核心闭环是：

```text
DiagnosticQuestion
  → CHECKS
Observation
  → OBSERVATION_SUPPORTS {p_yes_given_cause}
Cause
  → 更新候选概率与下一轮子图
```

## Open WebUI与Ollama实例

```text
【故障】服务或配置连接失败
  →【原因】服务地址配置错误
  →【部署环境】Open WebUI容器访问宿主机Ollama
  →【服务】Open WebUI →【服务】Ollama →【端点】/api/tags

【问题】宿主机正常但容器访问失败吗
  →【观察】宿主机成功、容器失败
  → 条件概率支持【原因】服务地址配置错误

【部署环境】
  →【检查】从容器访问/api/tags
  →【修复】配置OLLAMA_BASE_URL
  →【风险】修改前保留原值
  →【来源】Docker、Open WebUI、Ollama官方文档
```

网页“图谱结构”页从当前运行图谱实时统计节点和关系数量，并列出27类受控关系；“固定案例”页展示这些类型和关系怎样进入一条真实诊断轨迹。
