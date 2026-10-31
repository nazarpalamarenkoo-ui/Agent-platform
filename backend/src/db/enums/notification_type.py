from enum import Enum


class NotificationType(str, Enum):
    SKILL_ARCHIVED = "skill_archived"
    TOOL_ARCHIVED = "tool_archived"