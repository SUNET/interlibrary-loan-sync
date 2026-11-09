from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.state_audit_logs import StateAuditLogRepository
from ill_bridge.schemas.response.libris import StateAuditLogRead
from ill_bridge.services.state_audit_logs import StateAuditLogService

router = APIRouter()


def get_state_audit_log_service(
    session: AsyncSession = Depends(get_db),
) -> StateAuditLogService:
    return StateAuditLogService(StateAuditLogRepository(session))


@router.get("/state_audit_logs", response_model=list[StateAuditLogRead])
async def list_state_audit_logs(
    limit: int = 100,
    service: StateAuditLogService = Depends(get_state_audit_log_service),
) -> list[StateAuditLogRead]:
    rows = await service.list_state_audit_logs(limit=limit)
    return [StateAuditLogRead.model_validate(row) for row in rows]


@router.get("/state_audit_logs/{id}", response_model=StateAuditLogRead)
async def get_state_audit_log(
    id: UUID,
    service: StateAuditLogService = Depends(get_state_audit_log_service),
) -> StateAuditLogRead:
    row = await service.get_state_audit_log(id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="State audit log not found",
        )
    return StateAuditLogRead.model_validate(row)
