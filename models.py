from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, CheckConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

class User(Base):
    __tablename__ = "board_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))

class Post(Base):
    __tablename__ = "board_posts"
    __table_args__ = (
        CheckConstraint("length(trim(title)) between 1 and 200"),
        CheckConstraint("length(trim(content)) between 1 and 10000"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(ForeignKey("board_users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

