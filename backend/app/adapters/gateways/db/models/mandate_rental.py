from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.gateways.db.base import Base

if TYPE_CHECKING:
    from app.adapters.gateways.db.models.mandate import Mandate


class MandateRental(Base):
    __tablename__ = "mandate_rentals"

    # UniqueConstraint enforces the one-to-one: one rental record per mandate.
    __table_args__ = (
        UniqueConstraint("mandate_id", name="uq_mandate_rental_mandate_id"),
        Index("ix_mandate_rentals_availability_at", "availability_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mandate_id: Mapped[int] = mapped_column(
        ForeignKey("mandates.mandate_id", ondelete="CASCADE")
    )

    type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    rental_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Duration in months — use Integer; migrate to Interval if precision is needed.
    lease_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    availability_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    rent_net: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    rent_charges: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    security_deposit: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    payment_frequency: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Current effective rent (may differ from initial after renegotiation)
    effectivepricing_net: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    effectivepricing_charges: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    effectivepricing_changedat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    mandate: Mapped["Mandate"] = relationship(back_populates="rental")
