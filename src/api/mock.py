from fastapi import APIRouter

from services.oauth.yandex.schemas import YandexIdTokenData, YandexIdUserData

router = APIRouter()


@router.post("/yandex-token")
async def yandex_token_mock() -> YandexIdTokenData:
    return YandexIdTokenData(**{
        "token_type": "bearer",
        "access_token": "AQAAAACy1C6ZAAAAfa6vDLuItEy8pg-iIpnDxIs",
        "expires_in": 124234123534,
        "refresh_token": "1:GN686QVt0mmakDd9:A4pYuW9LGk0_UnlrMIWklkAuJkUWbq27loFekJVmSYrdfzdePBy7:A-2dHOmBxiXgajnD-kYOwQ",
        "scope": "login:info login:email login:avatar"
    })


@router.get("/yandex-user")
async def yandex_user_info_mock() -> YandexIdUserData:
    return YandexIdUserData(**{
        "login": "rock4ts",
        "id": "1000034426",
        "client_id": "4760187d81bc4b7799476b42b5103713",
        "psuid": "1.AAceCw.tbHgw5DtJ9_zeqPrk-Ba2w.qPWSRC5v2t2IaksPJgnge",
        "default_email": "rock4ts@yandex.ru",
        "first_name": "Artyom",
        "last_name": "Suhov",
        "display_name": "Artyom",
        "real_name": "Artyom Suhov",
        "sex": "male",
    })
