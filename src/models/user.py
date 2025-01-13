import datetime
import string
from secrets import choice as secrets_choice

from passlib.handlers.pbkdf2 import pbkdf2_sha256
from pydantic import UUID4
from sqlalchemy import JSON, ForeignKey, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class User(Base):
    __tablename__ = "users"

    password: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(nullable=False, unique=True)
    first_name: Mapped[str] = mapped_column(nullable=False, default="")
    last_name: Mapped[str] = mapped_column(nullable=False, default="")

    role_id: Mapped[UUID4 | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    role: Mapped["Role"] = relationship()

    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
    )
    oauth_accounts: Mapped[set["OAuthAccount"]] = relationship(back_populates="user")

    def set_password(self, raw_password: str | None = None) -> None:
        if raw_password is None:
            raw_password = self.generate_random_password()
        self.password = pbkdf2_sha256.hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return pbkdf2_sha256.verify(raw_password, self.password)

    def __repr__(self) -> str:
        return f"<User {self.email}>"

    @staticmethod
    def generate_random_password() -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets_choice(alphabet) for _ in range(16))


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"

    user_id: Mapped[UUID4] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user: Mapped[User] = relationship(back_populates="oauth_accounts")

    provider: Mapped[str]
    external_user_id: Mapped[str]
    access_data: Mapped[str] = mapped_column(JSON)

    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
    )


class Role(Base):
    __tablename__ = "roles"

    title: Mapped[str] = mapped_column(unique=True)
    system_role: Mapped[bool | None] = mapped_column(default=False)

    def __repr__(self) -> str:
        return f"<Role {self.title}>"
