from __future__ import annotations

from uuid import UUID

from ill_bridge.database.models import StateAuditLogs
from ill_bridge.repositories.state_audit_logs import StateAuditLogRepository


class StateAuditLogService:
    def __init__(self, repository: StateAuditLogRepository) -> None:
        self.repository = repository

    async def list_state_audit_logs(self, limit: int = 100) -> list[StateAuditLogs]:
        return await self.repository.list_all(limit=limit)

    async def get_state_audit_log(self, log_id: UUID) -> StateAuditLogs | None:
        return await self.repository.get_by_id(log_id)
