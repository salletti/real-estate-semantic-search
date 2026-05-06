from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.gateways.db.base import Base

if TYPE_CHECKING:
    from app.adapters.gateways.db.models.mandate import Mandate
    from app.adapters.gateways.db.models.property import Property


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    concession_slug: Mapped[str] = mapped_column(String(200), index=True)
    qualification_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50))
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    properties: Mapped[list["Property"]] = relationship(back_populates="advisor")
    mandates: Mapped[list["Mandate"]] = relationship(back_populates="agent")
