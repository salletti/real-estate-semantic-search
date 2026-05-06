from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.gateways.db.base import Base

if TYPE_CHECKING:
    from app.adapters.gateways.db.models.mandate import Mandate


class MandateSale(Base):
    __tablename__ = "mandate_sales"

    # UniqueConstraint enforces the one-to-one: one sale record per mandate.
    __table_args__ = (
        UniqueConstraint("mandate_id", name="uq_mandate_sale_mandate_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mandate_id: Mapped[int] = mapped_column(
        ForeignKey("mandates.mandate_id", ondelete="CASCADE")
    )

    type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Agreed price at mandate signature
    pricing_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    pricing_netprice: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # Current effective price (may differ after renegotiation)
    effectivepricing_price: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    effectivepricing_netprice: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    effectivepricing_changedat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    mandate: Mapped["Mandate"] = relationship(back_populates="sale")
