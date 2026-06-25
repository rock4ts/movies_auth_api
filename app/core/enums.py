from enum import StrEnum


class AccessLabel(StrEnum):
    FREE = "free"
    PREMIUM = "premium"
    VIP = "vip"


class OAuthProvider(StrEnum):
    YANDEX = "yandex"
