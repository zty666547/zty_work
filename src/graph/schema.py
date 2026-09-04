"""培养方案知识图谱的 Schema 定义。"""
from __future__ import annotations


ENTITY_TYPES = [
    "Program",
    "Course",
    "CourseCategory",
    "Semester",
    "Department",
    "GraduationRequirement",
    "Concept",
    "CourseGroup",
    "Rule",
    "DocumentSource",
]

RELATION_SIGNATURES = {
    "HAS_COURSE": ("Program", "Course"),
    "HAS_REQUIREMENT": ("Program", "GraduationRequirement"),
    "BELONGS_TO_CATEGORY": ("Course", "CourseCategory"),
    "OFFERED_IN": ("Course", "Semester"),
    "TAUGHT_BY": ("Course", "Department"),
    "SUPPORTS_REQUIREMENT": ("Course", "GraduationRequirement"),
    "HAS_RULE": ("Program", "Rule"),
    "GOVERNS_CATEGORY": ("Rule", "CourseCategory"),
    "GOVERNS_GROUP": ("Rule", "CourseGroup"),
    "GOVERNS_CONCEPT": ("Rule", "Concept"),
    "ALLOWS_OPTION": ("Rule", "CourseGroup"),
    "SUPPORTED_BY": ("Rule", "DocumentSource"),
    "CATEGORY_IN_DOMAIN": ("CourseCategory", "Concept"),
    "HAS_NATURE": ("CourseCategory", "Concept"),
    "CONTAINS_GROUP": ("CourseGroup", "CourseGroup"),
    "COUNTS_TOWARD": ("CourseGroup", "CourseCategory"),
    "DEFINED_BY": ("Concept", "DocumentSource"),
}

RELATION_TYPES = list(RELATION_SIGNATURES)
