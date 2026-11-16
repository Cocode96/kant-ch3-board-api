import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

load_dotenv(Path(__file__).with_name(".env"))
url = os.environ.get("DATABASE_URL", "")
if not url.startswith("postgresql+asyncpg://") and not (
    os.environ.get("BOARD_TESTING") == "1" and url == "sqlite+aiosqlite:///:memory:"
):
    raise RuntimeError("별도 PostgreSQL의 DATABASE_URL을 설정하세요.")
engine = create_async_engine(url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with Session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

