from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.gateways.db.base import Base

if TYPE_CHECKING:
    from app.adapters.gateways.db.models.agent import Agent
    from app.adapters.gateways.db.models.mandate_rental import MandateRental
    from app.adapters.gateways.db.models.mandate_sale import MandateSale
    from app.adapters.gateways.db.models.property import Property


class Mandate(Base):
    __tablename__ = "mandates"

    __table_args__ = (
        UniqueConstraint("order_number", name="uq_mandate_order_number"),
        Index("ix_mandates_property_id", "property_id"),
        Index("ix_mandates_agent_id", "agent_id"),
        Index("ix_mandates_validated_at", "validated_at"),
    )

    mandate_id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(100))

    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="RESTRICT")
    )
    agent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    canceled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exclusivity_terminated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Denormalized snapshot — mandate records must remain coherent
    # even if the linked property is later updated or archived.
    property_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    property_surface: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    property_designation: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )

    property: Mapped["Property"] = relationship(back_populates="mandates")
    agent: Mapped[Optional["Agent"]] = relationship(back_populates="mandates")
    sale: Mapped[Optional["MandateSale"]] = relationship(
        back_populates="mandate", uselist=False, cascade="all, delete-orphan"
    )
    rental: Mapped[Optional["MandateRental"]] = relationship(
        back_populates="mandate", uselist=False, cascade="all, delete-orphan"
    )
