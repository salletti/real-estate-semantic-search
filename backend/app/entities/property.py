# TEMPORARY: Using SQLAlchemy model as domain entity.
# This will be replaced by a pure domain entity + mapper in Phase 3.
from app.adapters.gateways.db.models.property import Property

__all__ = ["Property"]
