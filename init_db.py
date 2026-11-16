"""새 개인 테스트 DB에 테이블을 만든다. 앱 시작 시 자동 실행하지 않는다."""
import asyncio
from database import Base, engine
import models

async def main():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("board_users, board_posts tables created")

if __name__ == "__main__":
    asyncio.run(main())

