# DebugPath知识图谱数据字典

| 实体 | 含义 | 示例 |
|---|---|---|
| Issue | 用户可感知的故障场景 | PyTorch无法使用GPU |
| Cause | 可能根因 | 安装了CPU版PyTorch |
| Observation | 可以回答或检查的现象 | `torch.version.cuda`不是None |
| DiagnosticQuestion | 系统向用户提出的问题 | PyTorch是否包含CUDA构建 |
| DiagnosticCheck | 只读或低副作用检查 | 查看PyTorch构建信息 |
| RepairAction | 检查通过后才能采用的操作 | 安装匹配计算平台的PyTorch |
| Package | 涉及的软件包 | PyTorch |
| Platform | 操作系统或运行平台 | macOS |
| VersionConstraint | 事实成立的版本条件 | PyTorch计算平台构建约束 |
| Risk | 操作风险等级 | 中风险 |
| DocumentSource | 官方证据来源 | PyTorch本地安装指南 |
| EvidenceChunk | 可独立检索的具体证据片段 | E017-macOS使用MPS |

关键关系：

```text
Issue -HAS_POSSIBLE_CAUSE-> Cause
Issue -HAS_QUESTION-> DiagnosticQuestion
DiagnosticQuestion -CHECKS-> Observation
Observation -OBSERVATION_SUPPORTS-> Cause
Cause -CAUSE_CHECKED_BY-> DiagnosticCheck
Cause -CAUSE_RESOLVED_BY-> RepairAction
RepairAction -REPAIR_REQUIRES-> DiagnosticCheck
RepairAction -REPAIR_HAS_RISK-> Risk
Cause/Check/Repair -...SUPPORTED_BY-> DocumentSource
DocumentSource -SOURCE_CONTAINS_CHUNK-> EvidenceChunk
EvidenceChunk -CHUNK_SUPPORTS_CAUSE-> Cause
EvidenceChunk -CHUNK_SUPPORTS_CHECK-> DiagnosticCheck
EvidenceChunk -CHUNK_SUPPORTS_REPAIR-> RepairAction
```

`HAS_POSSIBLE_CAUSE.prior`表示场景内启发式先验；`OBSERVATION_SUPPORTS.p_yes_given_cause`表示原因成立时观察结果为“是”的条件概率。它们只用于原型排序，后续需要通过标注案例校准。

`EvidenceChunk`保存`chunk_id`、改写后的证据文本、关键词、来源标题、URL、章节和适用平台。当前30条片段均为官方文档或公开问题的简短转述，不保存整篇网页，也不把公开问题中的个别现象直接当成通用结论。
