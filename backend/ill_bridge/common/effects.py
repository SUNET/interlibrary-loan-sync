"""Plan external effects owed by an ILL workflow transition.

Rules are declarative configuration selected by direction and state transition.
The planner returns concrete, permitted effects so the polling transaction can
write them to ``effect_queue`` without re-deriving intent in a later worker.
"""

from __future__ import annotations

from enum import StrEnum

from ill_bridge.common.enums import ILLDirection, ProviderCommand
from ill_bridge.common.models import ProviderRequestObservation, ReceivingLibrary
from ill_bridge.common.states import ProcessingState, WorkflowState
from ill_bridge.database.models import Tenants
from ill_bridge.providers.base import IllProvider


class EffectKind(StrEnum):
    FOLIO_ADD_REQUESTING_LIBRARY = "FOLIO_ADD_REQUESTING_LIBRARY"
    FOLIO_PROVISION_ITEM = "FOLIO_PROVISION_ITEM"
    FOLIO_OPEN_LOAN = "FOLIO_OPEN_LOAN"
    FOLIO_CLOSE_LOAN = "FOLIO_CLOSE_LOAN"
    FOLIO_RENEW_LOAN = "FOLIO_RENEW_LOAN"
    NOTIFY_PATRON_PICKUP = "NOTIFY_PATRON_PICKUP"
    PROVIDER_ACCEPT = "PROVIDER_ACCEPT"
    PROVIDER_REJECT = "PROVIDER_REJECT"
    PROVIDER_CANCEL = "PROVIDER_CANCEL"
    PROVIDER_REVIEW_NEW_REQUEST = "PROVIDER_REVIEW_NEW_REQUEST"


_PROVIDER_EFFECTS = frozenset(
    {
        EffectKind.PROVIDER_ACCEPT,
        EffectKind.PROVIDER_REJECT,
        EffectKind.PROVIDER_CANCEL,
        EffectKind.PROVIDER_REVIEW_NEW_REQUEST,
    }
)

_PLAN: dict[
    tuple[ILLDirection, WorkflowState | None, WorkflowState], tuple[EffectKind, ...]
] = {
    (ILLDirection.BORROWING, WorkflowState.REQUESTED, WorkflowState.ACCEPTED): (
        EffectKind.FOLIO_PROVISION_ITEM,
    ),
    (ILLDirection.BORROWING, WorkflowState.RECEIVED, WorkflowState.READY_FOR_PICKUP): (
        EffectKind.NOTIFY_PATRON_PICKUP,
    ),
    (ILLDirection.BORROWING, WorkflowState.READY_FOR_PICKUP, WorkflowState.ON_LOAN): (
        EffectKind.FOLIO_OPEN_LOAN,
    ),
    (ILLDirection.BORROWING, WorkflowState.ON_LOAN, WorkflowState.RETURN_PENDING): (
        EffectKind.FOLIO_CLOSE_LOAN,
    ),
    (ILLDirection.LENDING, WorkflowState.REQUESTED, WorkflowState.REJECTED): (
        EffectKind.PROVIDER_REJECT,
    ),
    (ILLDirection.LENDING, WorkflowState.REQUESTED, WorkflowState.ACCEPTED): (
        EffectKind.PROVIDER_ACCEPT,
    ),
    # (ILLDirection.LENDING, None, WorkflowState.CANCELLED): (
    #     EffectKind.PROVIDER_CANCEL,
    #     EffectKind.FOLIO_CLOSE_LOAN
    # ),
    (ILLDirection.LENDING, WorkflowState.ACCEPTED, WorkflowState.CANCELLED): (
        EffectKind.PROVIDER_CANCEL,
        EffectKind.FOLIO_CLOSE_LOAN,
    ),
    (ILLDirection.LENDING, WorkflowState.REQUESTED, WorkflowState.CANCELLED): (
        EffectKind.PROVIDER_CANCEL,
        EffectKind.FOLIO_CLOSE_LOAN,
    ),
    (ILLDirection.LENDING, WorkflowState.ACCEPTED, WorkflowState.ON_LOAN): (
        EffectKind.FOLIO_OPEN_LOAN,
    ),
    (ILLDirection.LENDING, None, WorkflowState.REQUESTED): (
        EffectKind.FOLIO_ADD_REQUESTING_LIBRARY,
        EffectKind.PROVIDER_REVIEW_NEW_REQUEST,
    ),
    # --- Lending lifecycle (see common/transitions.py) ---
    # ARRIVED is observational only; it does not queue external effects.
    (ILLDirection.LENDING, WorkflowState.RESERVED, WorkflowState.IN_TRANSIT): (
        EffectKind.FOLIO_OPEN_LOAN,
    ),
    (ILLDirection.LENDING, WorkflowState.ACCEPTED, WorkflowState.IN_TRANSIT): (
        EffectKind.FOLIO_OPEN_LOAN,
    ),
    # Requesting library asked for a renewal: extend the FOLIO loan.
    (ILLDirection.LENDING, WorkflowState.RECEIVED, WorkflowState.RENEWAL_REQUESTED): (
        EffectKind.FOLIO_RENEW_LOAN,
    ),
    # Item is back at our library: check it in in FOLIO.
    (ILLDirection.LENDING, WorkflowState.RETURN_IN_TRANSIT, WorkflowState.RETURNED): (
        EffectKind.FOLIO_CLOSE_LOAN,
    ),
}


def plan_effects(
    observation: ProviderRequestObservation,
    *,
    from_workflow_state: WorkflowState | None,
    to_workflow_state: WorkflowState,
    processing_state: ProcessingState,
    provider: IllProvider,
) -> tuple[EffectKind, ...]:
    """Return the permitted effects owed by an accepted provider observation."""
    if from_workflow_state == to_workflow_state:
        # No transition, no effects. This is a no-op observation.
        return ()

    if processing_state in {
        ProcessingState.NEEDS_REVIEW,
        ProcessingState.CONFLICT,
    }:
        # We don't plan effects for observations that need review or are in conflict.
        return ()

    effects: list[EffectKind] = []
    for effect_kind in _PLAN.get(
        (observation.direction, from_workflow_state, to_workflow_state), ()
    ):
        if (
            effect_kind is EffectKind.FOLIO_PROVISION_ITEM
            and observation.patron_reference is None
        ):
            print("CASE 1: No patron reference, skipping FOLIO_PROVISION_ITEM effect.")
            continue
        if effect_kind in _PROVIDER_EFFECTS:
            command = ProviderCommand(effect_kind.value)
            print(
                f"Checking if provider supports command {command} for effect {effect_kind}."
            )
            if (
                not provider.writes_enabled
                or command not in provider.capabilities.commands
            ):
                print(
                    f"CASE 2: Provider writes disabled or command {command} not supported, skipping {effect_kind} effect."
                )
                continue
        effects.append(effect_kind)

    return tuple(effects)


async def apply_effects(
    effects, observation: ProviderRequestObservation, folio_client, tenant: Tenants
):
    from ill_bridge.common.folio_client import (
        create_folio_requesting_library,
    )
    from ill_bridge.config import FOLIO_TENANT_PATRON_GROUPS

    receiving_library: ReceivingLibrary = observation.receiving_library
    for effect in effects:
        if effect == EffectKind.FOLIO_ADD_REQUESTING_LIBRARY:
            patron_group = FOLIO_TENANT_PATRON_GROUPS[tenant.folio_tenant_key]
            patron_group_id = patron_group.uuid

            response = await create_folio_requesting_library(
                client=folio_client,
                receiving_library=receiving_library,
                patron_group_id=patron_group_id,
            )
            return response
        elif effect == EffectKind.FOLIO_PROVISION_ITEM:
            # Implement logic to provision item in FOLIO
            pass
