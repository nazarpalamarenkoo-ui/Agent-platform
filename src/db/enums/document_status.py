from enum import Enum

class DocumentStatus(str, Enum):
    
    PENDING = 'pending'
    PROCESSING = 'processing'
    INDEXED = 'indexed'
    FAILED = 'failed'