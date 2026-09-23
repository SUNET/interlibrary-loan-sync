from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
ProviderId = NewType("ProviderId", UUID)
