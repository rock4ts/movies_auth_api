import uuid
from datetime import UTC, datetime

from pydantic import UUID4
from sqlalchemy import (
    JSON,
    TIMESTAMP,
    UUID,
    ForeignKey,
    Index,
    MetaData,
    PrimaryKeyConstraint,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.enums import AccessLabel


class ProjectBase(DeclarativeBase):
    __abstract__ = True

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class ProjectBaseCreatedUpdated(ProjectBase):
    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.now(UTC),
        onupdate=datetime.now(UTC),
    )


class ProjectBaseWithId(ProjectBase):
    __abstract__ = True

    id: Mapped[UUID4] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )


class User(ProjectBaseWithId, ProjectBaseCreatedUpdated):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(nullable=False)
    token_version: Mapped[int] = mapped_column(nullable=False, default=1)
    first_name: Mapped[str] = mapped_column(nullable=False, default="")
    last_name: Mapped[str] = mapped_column(nullable=False, default="")

    role_id: Mapped[UUID4 | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    role: Mapped["Role"] = relationship()
    is_superuser: Mapped[bool] = mapped_column(default=False)

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.now(UTC),
        onupdate=datetime.now(UTC),
    )
    oauth_accounts: Mapped[set["OAuthAccount"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class Role(ProjectBaseWithId, ProjectBaseCreatedUpdated):
    __tablename__ = "roles"

    title: Mapped[str] = mapped_column(unique=True)
    access_labels: Mapped[list[AccessLabel]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    def __repr__(self) -> str:
        return f"<Role {self.title}>"


class LoginHistory(ProjectBase):
    __tablename__ = "login_history"
    __table_args__ = (
        PrimaryKeyConstraint("id", "logged_in_at"),
        Index("ix_login_history_user_id_logged_in_at", "user_id", "logged_in_at"),
        Index("ix_login_history_logged_in_at", "logged_in_at"),
        {"postgresql_partition_by": "RANGE (logged_in_at)"},
    )

    id: Mapped[UUID4] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    ip_address: Mapped[str] = mapped_column(nullable=False)
    user_agent: Mapped[str | None] = mapped_column(nullable=True)
    device_id: Mapped[str | None] = mapped_column(nullable=True)
    logged_in_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<LoginHistory user_id={self.user_id}, "
            f"timestamp={self.logged_in_at}, "
            f"ip_address={self.ip_address}, user_agent={self.user_agent}>"
        )


class OAuthAccount(ProjectBaseWithId, ProjectBaseCreatedUpdated):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    provider: Mapped[str] = mapped_column(nullable=False)
    provider_user_id: Mapped[str] = mapped_column(nullable=False)

    user_id: Mapped[UUID4] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user: Mapped[User] = relationship(back_populates="oauth_accounts")
