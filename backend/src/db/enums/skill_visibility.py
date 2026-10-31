from enum import Enum


class SkillVisibility(str, Enum):
    PRIVATE = "private"
    PENDING_REVIEW = "pending_review"
    GLOBAL = "global"