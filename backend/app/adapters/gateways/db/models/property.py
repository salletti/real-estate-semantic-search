from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.gateways.db.base import Base

if TYPE_CHECKING:
    from app.adapters.gateways.db.models.agent import Agent
    from app.adapters.gateways.db.models.description import Description
    from app.adapters.gateways.db.models.mandate import Mandate
    from app.adapters.gateways.db.models.property_listing import PropertyListing


class Property(Base):
    __tablename__ = "properties"

    __table_args__ = (
        Index("ix_properties_city", "city"),
        Index("ix_properties_status", "status"),
        Index("ix_properties_type", "type"),
        Index("ix_properties_mandate_price", "mandate_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    advisor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    type: Mapped[str] = mapped_column(String(50))
    sub_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50))
    transaction_type: Mapped[str] = mapped_column(String(50))

    city: Mapped[str] = mapped_column(String(100))
    postal_code: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(50), server_default="FR")

    # Nullable: not all properties have geocoding at ingestion time
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    rooms_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    surface_area: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    mandate_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_prestige: Mapped[bool] = mapped_column(Boolean, server_default="false")

    advisor: Mapped[Optional["Agent"]] = relationship(back_populates="properties")
    descriptions: Mapped[list["Description"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    listings: Mapped[list["PropertyListing"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    mandates: Mapped[list["Mandate"]] = relationship(back_populates="property")
