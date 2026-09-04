# 数据字典

## 实体

| 类型 | 关键属性 | 示例 |
| --- | --- | --- |
| Program | institution、duration_years、minimum_credits、aliases | 2024级人工智能专业 |
| Course | code、credits、total_hours、required、aliases | 知识工程 |
| CourseCategory | aliases、required、required_credits、description | 专业核心课 / 文化素质选修课 |
| Semester | order、aliases | 第4学期 / 大二下 |
| Department | aliases | 智能与计算学部 |
| GraduationRequirement | 暂无专有属性 | 工程知识 |
| Concept | dimension、definition、aliases | 通识教育 / 选修课程性质 |
| CourseGroup | definition、selection_mode、aliases | 四史类课程 |
| Rule | rule_type、statement、scope、verification_status | 2024级思政选修课程组要求 |
| DocumentSource | publisher、source_tier、scope、url | 2024级人工智能专业培养方案原文 |

## 关系

| 关系 | 起点 → 终点 | 含义 |
| --- | --- | --- |
| HAS_COURSE | Program → Course | 专业培养方案包含课程 |
| HAS_REQUIREMENT | Program → GraduationRequirement | 培养方案包含毕业要求 |
| BELONGS_TO_CATEGORY | Course → CourseCategory | 课程所属类别 |
| OFFERED_IN | Course → Semester | 建议修读学期 |
| TAUGHT_BY | Course → Department | 开课单位 |
| SUPPORTS_REQUIREMENT | Course → GraduationRequirement | 课程对毕业要求的支撑关系（预留） |
| HAS_RULE | Program → Rule | 专业适用的培养或选课规则 |
| GOVERNS_CATEGORY | Rule → CourseCategory | 规则约束课程类别 |
| GOVERNS_GROUP | Rule → CourseGroup | 规则约束课程组 |
| GOVERNS_CONCEPT | Rule → Concept | 规则解释或约束概念 |
| ALLOWS_OPTION | Rule → CourseGroup | 规则允许选择的课程组 |
| SUPPORTED_BY | Rule → DocumentSource | 规则的证据来源 |
| CATEGORY_IN_DOMAIN | CourseCategory → Concept | 课程类别所属培养领域 |
| HAS_NATURE | CourseCategory → Concept | 课程类别的必修/选修性质 |
| CONTAINS_GROUP | CourseGroup → CourseGroup | 课程组包含子课程组 |
| COUNTS_TOWARD | CourseGroup → CourseCategory | 课程组学分可计入的类别 |
| DEFINED_BY | Concept → DocumentSource | 概念定义依据 |

## 数据边界

- 当前版本：2024级人工智能专业。
- 当前规模：39 门代表性课程、8 个学期、7 个课程类别、14 项毕业要求、5 条规则和 4 个来源节点。
- 当前未录入：先修关系、每个年级的不同版本、实时开课状态、个人成绩。
- `SUPPORTS_REQUIREMENT` 只有在获得可靠课程支撑矩阵后才写入。
- 学期性规则必须保留 `scope`，不能泛化为永久规则。
- `verification_status` 标记为“待原始通知复核”的内容只能作为有条件证据。
