from typing import Annotated

import typer
from pwdlib import PasswordHash
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import db_settings
from app.db.models import User

app = typer.Typer()
password_hash = PasswordHash.recommended()
engine = create_engine(url=str(db_settings.sync_url))
session_maker = sessionmaker(bind=engine)


# Асинхронная команда для создания суперпользователя
@app.command()
def create_superuser(
    email: Annotated[
        str,
        typer.Option(
            envvar="SUPERUSER_EMAIL",
            prompt="Email пользователя",
            help="Email пользователя",
        ),
    ],
    password: Annotated[
        str,
        typer.Option(
            envvar="SUPERUSER_PASSWORD",
            prompt=True,
            hide_input=True,
            help="Пароль пользователя",
        ),
    ],
):
    with session_maker() as session:
        user_checkq = session.execute(select(User).where(User.email == email))
        user_exists = user_checkq.scalars().first()
        if user_exists:
            typer.echo(f"Пользователь с email {email} уже существует")
            return

        user = User(
            email=email,
            password_hash=password_hash.hash(password),
            is_superuser=True,
            role_id=None,
        )
        session.add(user)
        try:
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            typer.echo(f"Ошибка при создании суперпользователя: {str(e)}")


if __name__ == "__main__":
    app()
