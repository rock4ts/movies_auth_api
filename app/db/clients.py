from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings, db_settings, redis_settings

from redis.asyncio import Redis

# Persistance DB
engine = create_async_engine(db_settings.async_url, echo=settings.debug, future=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

# Cache DB
redis = Redis(host=redis_settings.host, port=redis_settings.port)
