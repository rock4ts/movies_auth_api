from typing import Any, List, Type, Union


from sqlalchemy import BooleanClauseList, Column, ColumnElement, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.interfaces import ORMOption
from sqlalchemy.orm.attributes import InstrumentedAttribute

import models


class AsyncBaseRepository:

    async def get(self, *args, **kwargs) -> models.Base:
        raise NotImplementedError

    async def list(self, *args, **kwargs) -> models.Base:
        raise NotImplementedError

    async def add(self, *args, **kwargs) -> models.Base:
        raise NotImplementedError

    async def update(self, *args, **kwargs) -> CursorResult[Any]:
        raise NotImplementedError

    async def delete(self, *args, **kwargs) -> CursorResult[Any]:
        raise NotImplementedError


class AsyncSqlAlchemyRepository(AsyncBaseRepository):

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        model: Type[models.Base],
        filters: List[Union[ColumnElement[bool], BooleanClauseList]] = [],
        options: List[ORMOption] = [],
        joins: List[InstrumentedAttribute] = [],
        join_filters: List[Union[ColumnElement[bool], BooleanClauseList]] = []
    ) -> models.Base | None:

        stmt = select(model)
        for filter_condition in filters:
            stmt = stmt.where(filter_condition)
        for join_target in joins:
            stmt = stmt.join(join_target)
        for j_filter_condition in join_filters:
            stmt = stmt.where(j_filter_condition)
        stmt = stmt.options(*options)

        async with self.session.begin():
            result = await self.session.execute(stmt)
            obj = result.scalars().first()

        return obj

    async def list(self, model: Type[models.Base]) -> list[models.Base]:
        async with self.session.begin():
            stmt = select(model)
            result = await self.session.execute(stmt)
            return result.scalars().all()

    async def add(self, model_obj: models.Base) -> models.Base:
        async with self.session.begin():
            self.session.add(model_obj)
            await self.session.flush()
            await self.session.refresh(model_obj)
        return model_obj

    async def update(
        self,
        model: Type[models.Base],
        filters: List[Union[ColumnElement[bool], BooleanClauseList]],
        update_kws: dict
    ) -> CursorResult[Any]:

        stmt = update(model)
        for filter_condition in filters:
            stmt = stmt.where(filter_condition)
        stmt = stmt.values(**update_kws)

        async with self.session.begin():
            result = await self.session.execute(stmt)
        return result

    async def delete(
        self, model: Type[models.Base], filter_col: Column, values: List[Any]
    ) -> CursorResult[Any]:

        if len(values) == 1:
            stmt = delete(model).where(filter_col == values[0])

        async with self.session.begin():
            result = await self.session.execute(stmt)
        return result
