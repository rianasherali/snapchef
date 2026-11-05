import os
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, ForeignKey, String, DateTime
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    restrictions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class IngredientList(Base):
    __tablename__ = "ingredient_lists"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ingredients: Mapped[list[str]] = mapped_column(ARRAY(String))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)