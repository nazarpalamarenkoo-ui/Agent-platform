from enum import Enum


class ToolVisibility(str, Enum):
    GLOBAL = "global"
    PRIVATE = "private"