from enum import IntEnum


class OAuthLoginServiceResult(IntEnum):
    SUCCESS = 1
    FAIL = 0
    ERROR = -1
    RECONCILE = 2
