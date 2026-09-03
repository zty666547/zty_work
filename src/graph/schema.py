"""培养方案知识图谱的 Schema 定义。"""
from __future__ import annotations


ENTITY_TYPES = [
    "Program",
    "Course",
    "CourseCategory",
    "Semester",
    "Department",
    "GraduationRequirement",
]

RELATION_SIGNATURES = {
    "HAS_COURSE": ("Program", "Course"),
    "HAS_REQUIREMENT": ("Program", "GraduationRequirement"),
    "BELONGS_TO_CATEGORY": ("Course", "CourseCategory"),
    "OFFERED_IN": ("Course", "Semester"),
    "TAUGHT_BY": ("Course", "Department"),
    "SUPPORTS_REQUIREMENT": ("Course", "GraduationRequirement"),
}

RELATION_TYPES = list(RELATION_SIGNATURES)
