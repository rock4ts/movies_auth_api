from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import db_settings, redis_settings, settings

# Persistance DB
engine = create_async_engine(db_settings.async_url, echo=settings.debug, future=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

# Cache DB
redis = Redis(host=redis_settings.host, port=redis_settings.port)
