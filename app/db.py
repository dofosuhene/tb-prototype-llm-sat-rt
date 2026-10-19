"""Datenbank (SQLite im Prototyp). Spaeter mit Dominiks Schema abgleichen und Alembic verwenden."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import DATENBANK_URL


class Base(DeclarativeBase):
    pass


class Eintrag(Base):
    """Eine Aufgabe oder Pruefung, die aus dem Freitext erkannt wurde."""
    __tablename__ = "eintrag"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    typ: Mapped[str] = mapped_column(String(20))          # Aufgabe | Pruefung
    fach: Mapped[str] = mapped_column(String(50))
    titel: Mapped[str] = mapped_column(String(200))
    termin: Mapped[datetime] = mapped_column(DateTime)
    lernminuten: Mapped[int] = mapped_column(Integer)
    erstellt: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    bloecke: Mapped[list["Lernblock"]] = relationship(
        back_populates="eintrag", cascade="all, delete-orphan", order_by="Lernblock.start")


class Lernblock(Base):
    """Ein geplanter Lernblock. erledigt=True zaehlt fuer den Readiness-Score."""
    __tablename__ = "lernblock"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    eintrag_id: Mapped[int] = mapped_column(ForeignKey("eintrag.id"))
    start: Mapped[datetime] = mapped_column(DateTime)
    ende: Mapped[datetime] = mapped_column(DateTime)
    erledigt: Mapped[bool] = mapped_column(Boolean, default=False)
    eintrag: Mapped[Eintrag] = relationship(back_populates="bloecke")

    @property
    def minuten(self) -> int:
        return int((self.ende - self.start).total_seconds() // 60)


def engine_erstellen(url: str = DATENBANK_URL):
    if url.startswith("sqlite"):
        extra = {"poolclass": StaticPool} if url == "sqlite://" else {}
        return create_engine(url, connect_args={"check_same_thread": False}, **extra)
    return create_engine(url)


engine = engine_erstellen()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
