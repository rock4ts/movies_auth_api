from enum import IntEnum, StrEnum, auto


class UserAcquireMethod(StrEnum):
    GET = auto()
    CREATE = auto()


class YandexAuthRedisPrefix(StrEnum):
    YALOGIN = auto()
    YATOKEN = auto()


class YandexLoginServiceResult(IntEnum):
    SUCCESS = 1
    FAIL = 0
    ERROR = -1
    RECONCILE = 2
