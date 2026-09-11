# DebugPath因果知识图谱设计

## 图谱解决什么问题

普通知识图谱可以表示“某个故障与哪些原因相关”。DebugPath还需要支持主动诊断，因此必须继续表达：什么观察支持某个原因、应当询问什么、如何确认、如何修复，以及结论适用于什么环境。

## 节点层次

| 层次 | 节点 | 作用 |
| --- | --- | --- |
| 故障入口 | `Issue` | 定义系统支持的故障族 |
| 候选解释 | `Cause` | 动态诊断需要排序的根因 |
| 用户证据 | `DiagnosticQuestion`、`Observation` | 把回答转换成概率证据 |
| 验证与处置 | `DiagnosticCheck`、`RepairAction`、`Risk` | 形成先检查、后修复的安全路径 |
| 适用条件 | `Package`、`Platform`、`VersionConstraint` | 防止跨平台、跨版本误用 |
| 证据来源 | `DocumentSource`、`EvidenceChunk` | 支持检索与结论追溯 |

## 关键因果链

```text
Issue
  ├─ HAS_POSSIBLE_CAUSE → Cause
  └─ HAS_QUESTION → DiagnosticQuestion
                         └─ CHECKS → Observation
                                          └─ OBSERVATION_SUPPORTS → Cause

Cause
  ├─ CAUSE_CHECKED_BY → DiagnosticCheck
  ├─ CAUSE_RESOLVED_BY → RepairAction
  ├─ VALID_ON / SUBJECT_TO_VERSION → 环境约束
  └─ CAUSE_SUPPORTED_BY → DocumentSource

RepairAction
  ├─ REPAIR_REQUIRES → DiagnosticCheck
  └─ REPAIR_HAS_RISK → Risk
```

这条链把三个课程部分连接起来：图谱保存因果与条件，检索推理更新`Cause`概率，知识注入只使用已经验证的检查、修复、风险和来源。

## 概率语义

`OBSERVATION_SUPPORTS`关系中的`p_yes_given_cause`表示：在某个原因真实成立时，相应问题得到肯定观察的概率。用户回答“是”时使用该值；回答“否”时使用其补概率；回答“不清楚”时不更新概率。

因此，这个关系不是“观察出现就绝对证明原因”的硬规则，而是带强度的诊断证据。第二阶段将只使用开发集案例估计这些概率，并在冻结测试集上验证。

## 内容扩展原则

- 每个原因至少具有一个观察、一个检查、一个修复和一个直接来源；
- 每个修复必须具有前置检查和风险说明；
- 平台或版本敏感的原因必须明确适用条件；
- 每个原因目标收集至少两个独立确认案例；
- 只有修复结果、维护者结论或可复现检查确认的案例才能参与准确率；
- 新增测试案例后不得根据测试结果修改先验、条件概率和停止阈值。
- 冻结测试案例不得作为BM25语料或图谱先验来源，否则会造成检索数据泄漏；只有开发集案例可以用于估计参数。

运行`python scripts/audit_second_stage.py`可以生成逐原因缺口报告。
