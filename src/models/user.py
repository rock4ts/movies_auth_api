import datetime
from passlib.handlers.pbkdf2 import pbkdf2_sha256
from pydantic import UUID4
from sqlalchemy import ForeignKey, TIMESTAMP
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

    def set_password(self, raw_password: str) -> None:
        self.password = pbkdf2_sha256.hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return pbkdf2_sha256.verify(raw_password, self.password)

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class Role(Base):
    __tablename__ = "roles"

    title: Mapped[str] = mapped_column(unique=True)
    system_role: Mapped[bool | None] = mapped_column(default=False)

    def __repr__(self) -> str:
        return f"<Role {self.title}>"
