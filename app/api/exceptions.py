from fastapi import HTTPException, status


class CredentialsHttpException(HTTPException):
    def __init__(self, detail: str = "Incorrect email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class RefreshHttpException(HTTPException):
    def __init__(self, detail: str = "Invalid refresh token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class RateLimitHttpException(HTTPException):
    def __init__(self, detail: str = "Too many requests", retry_after_seconds: int = 1):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(max(1, retry_after_seconds))},
        )


class RoleAlreadyExistsHttpError(HTTPException):
    def __init__(self, detail: str = "Role already exists"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


class UserNotFoundHttpError(HTTPException):
    def __init__(self, detail: str = "User not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class RoleNotFoundHttpError(HTTPException):
    def __init__(self, detail: str = "Role not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class ProtectedRoleHttpError(HTTPException):
    def __init__(self, detail: str = "Default role is protected"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


class WrongPasswordHttpError(HTTPException):
    def __init__(self, detail: str = "Wrong password"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


class OAuthStateHttpException(HTTPException):
    def __init__(self, detail: str = "OAuth state is invalid or expired"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


class OAuthProviderHttpException(HTTPException):
    def __init__(self, detail: str = "OAuth provider is temporarily unavailable"):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )


class OAuthCallbackHttpException(HTTPException):
    def __init__(self, detail: str = "OAuth callback failed"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )
