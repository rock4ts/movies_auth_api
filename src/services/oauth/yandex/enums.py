from enum import StrEnum, auto


class UserAcquireMethod(StrEnum):
    GET = auto()
    CREATE = auto()


class YandexAuthRedisPrefix(StrEnum):
    YALOGIN = auto()
    YATOKEN = auto()
