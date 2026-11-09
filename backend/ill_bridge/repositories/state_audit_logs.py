from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.models import StateAuditLogs


class StateAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, limit: int = 100) -> list[StateAuditLogs]:
        result = await self._session.execute(
            select(StateAuditLogs)
            .order_by(desc(StateAuditLogs.recorded_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, log_id: UUID) -> StateAuditLogs | None:
        result = await self._session.execute(
            select(StateAuditLogs).where(StateAuditLogs.id == log_id)
        )
        return result.scalar_one_or_none()
