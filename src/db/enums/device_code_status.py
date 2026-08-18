from enum import Enum

class DeviceStatus(str,Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = 'rejected'
    EXPIRED = 'expired'