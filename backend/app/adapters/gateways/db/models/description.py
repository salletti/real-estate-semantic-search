from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.gateways.db.base import Base

if TYPE_CHECKING:
    from app.adapters.gateways.db.models.property import Property


class Description(Base):
    __tablename__ = "descriptions"

    # Composite unique: one description per locale per property
    __table_args__ = (
        UniqueConstraint("property_id", "locale", name="uq_description_property_locale"),
        Index("ix_descriptions_property_id", "property_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE")
    )
    locale: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    property: Mapped["Property"] = relationship(back_populates="descriptions")
