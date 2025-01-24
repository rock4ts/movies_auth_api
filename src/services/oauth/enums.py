from enum import IntEnum, StrEnum, auto


class OAuthLoginServiceResult(IntEnum):
    SUCCESS = 1
    FAIL = 0
    ERROR = -1
    RECONCILE = 2


class UserAcquireMethod(StrEnum):
    GET = auto()
    CREATE = auto()
