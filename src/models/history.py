import uuid
from datetime import datetime, timezone

from pydantic import UUID4
from sqlalchemy import TIMESTAMP, UUID, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def create_partition(target, connection, **kw) -> None:  # noqa: ANN001, ANN003
    """Create initial partitions based on date ranges."""

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS login_history_2025_01
            PARTITION OF login_history
            FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS login_history_2025_02
            PARTITION OF login_history
            FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
            """
        )
    )


class LoginHistory(Base):
    __tablename__ = "login_history"
    __table_args__ = (
        UniqueConstraint('id', 'created_at'),
        {
            "postgresql_partition_by": "RANGE (created_at)",
            "listeners": [("after_create", create_partition)],
        }
    )
    id: Mapped[UUID4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.now(timezone.utc),
        primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="cascade"), nullable=False
    )
    ip_address: Mapped[str] = mapped_column(nullable=False)
    user_agent: Mapped[str] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return (
            f"<LoginHistory user_id={self.user_id}, "
            f"timestamp={self.created_at}, "
            f"ip_address={self.ip_address}, user_agent={self.user_agent}>"
        )
