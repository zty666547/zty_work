# 数据字典

## 实体

| 类型 | 关键属性 | 示例 |
| --- | --- | --- |
| Program | institution、duration_years、minimum_credits、aliases | 2023级人工智能专业 |
| Course | code、credits、total_hours、required、aliases | 知识工程 |
| CourseCategory | aliases | 专业核心课 |
| Semester | order、aliases | 第4学期 / 大二下 |
| Department | aliases | 智能与计算学部 |
| GraduationRequirement | 暂无专有属性 | 工程知识 |

## 关系

| 关系 | 起点 → 终点 | 含义 |
| --- | --- | --- |
| HAS_COURSE | Program → Course | 专业培养方案包含课程 |
| HAS_REQUIREMENT | Program → GraduationRequirement | 培养方案包含毕业要求 |
| BELONGS_TO_CATEGORY | Course → CourseCategory | 课程所属类别 |
| OFFERED_IN | Course → Semester | 建议修读学期 |
| TAUGHT_BY | Course → Department | 开课单位 |
| SUPPORTS_REQUIREMENT | Course → GraduationRequirement | 课程对毕业要求的支撑关系（预留） |

## 数据边界

- 当前版本：2023级人工智能专业。
- 当前规模：39 门代表性课程、8 个学期、5 个课程类别、3 个开课单位、14 项毕业要求。
- 当前未录入：先修关系、每个年级的不同版本、实时开课状态、个人成绩。
- `SUPPORTS_REQUIREMENT` 只有在获得可靠课程支撑矩阵后才写入。

