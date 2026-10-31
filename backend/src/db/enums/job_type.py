from enum import Enum

class JobType(str, Enum):
    DISCOVERY_INGEST = "discovery_ingest"
    SKILL_GENERATION = "skill_generation"
    NOTIFY_SKILL_ARCHIVED = "notify_skill_archived"


