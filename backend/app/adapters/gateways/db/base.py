from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base — import all models here so Alembic auto-detects them."""
    pass
