from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.gateways.db.base import Base

if TYPE_CHECKING:
    from app.adapters.gateways.db.models.property import Property


class PropertyListing(Base):
    __tablename__ = "property_listings"

    __table_args__ = (Index("ix_property_listings_property_id", "property_id"),)

    property_listing_id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )

    first_publish_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_publish_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unpublished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    broadcast_mode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Kept as Text — ambiguous in spec (city list? GeoJSON? zone name?).
    # Migrate to PostGIS geometry or JSONB when the shape is confirmed.
    geography: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    show_price: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    property: Mapped["Property"] = relationship(back_populates="listings")
