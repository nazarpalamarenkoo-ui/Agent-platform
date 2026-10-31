from enum import Enum


class ToolAuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    OAUTH = "oauth"