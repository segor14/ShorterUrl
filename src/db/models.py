from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, UniqueConstraint, ForeignKey, Text
from datetime import datetime


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class User(Base):
    __tablename__ = "user"
    username: Mapped[str] = mapped_column(String, unique=True, index=True)

    password_hash: Mapped[str] = mapped_column(String)

    urls: Mapped[list["ShortUrl"]] = relationship(back_populates="owner")


class ShortUrl(Base):
    __tablename__ = "short_url"
    original_url: Mapped[str] = mapped_column(String)
    short_code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    redirects_count: Mapped[int] = mapped_column(Integer, default=0)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    owner = relationship("User", back_populates="urls")
    __table_args__ = (UniqueConstraint("original_url", name="url_unique_constraint"), )
