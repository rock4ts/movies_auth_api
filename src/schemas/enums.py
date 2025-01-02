from enum import IntEnum, StrEnum, auto


class SystemRoles(StrEnum):
    SUPERUSER = auto()
    ADMIN = auto()


class ServiceWorkResults(IntEnum):
    SUCCESS = 1
    FAIL = 0
    ERROR = -1
