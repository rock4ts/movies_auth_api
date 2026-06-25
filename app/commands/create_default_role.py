import typer
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import DEFAULT_ROLE_ACCESS_LABELS, DEFAULT_ROLE_TITLE, db_settings
from app.db.models import Role

app = typer.Typer()
engine = create_engine(url=str(db_settings.sync_url))
session_maker = sessionmaker(bind=engine)


@app.command()
def create_default_role():
    with session_maker() as session:
        role_checkq = session.execute(select(Role).where(Role.title == DEFAULT_ROLE_TITLE))
        role_exists = role_checkq.scalars().first()
        if role_exists:
            typer.echo(f"Роль с названием {DEFAULT_ROLE_TITLE} уже существует")
            return

        role = Role(
            title=DEFAULT_ROLE_TITLE,
            access_labels=list(DEFAULT_ROLE_ACCESS_LABELS),
        )
        session.add(role)
        try:
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            typer.echo(f"Ошибка при создании роли по умолчанию: {str(e)}")


if __name__ == "__main__":
    app()
