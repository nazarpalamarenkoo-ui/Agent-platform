from enum import Enum

class DiscoveredDocumentDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"