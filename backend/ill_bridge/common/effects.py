"""Plan external effects owed by an ILL workflow transition.

Rules are declarative configuration selected by direction and state transition.
The planner returns concrete, permitted effects so the polling transaction can
write them to ``effect_queue`` without re-deriving intent in a later worker.
"""

from __future__ import annotations

from enum import StrEnum
from ill_bridge.common.enums import ILLDirection, ProviderCommand
from ill_bridge.common.models import ProviderRequestObservation
from ill_bridge.common.states import ProcessingState, WorkflowState
from ill_bridge.providers.base import IllProvider


class EffectKind(StrEnum):
    FOLIO_PROVISION_ITEM = "FOLIO_PROVISION_ITEM"
    FOLIO_OPEN_LOAN = "FOLIO_OPEN_LOAN"
    FOLIO_CLOSE_LOAN = "FOLIO_CLOSE_LOAN"
    NOTIFY_PATRON_PICKUP = "NOTIFY_PATRON_PICKUP"
    PROVIDER_ACCEPT = "PROVIDER_ACCEPT"
    PROVIDER_REJECT = "PROVIDER_REJECT"
    PROVIDER_CANCEL = "PROVIDER_CANCEL"


_PROVIDER_EFFECTS = frozenset(
    {EffectKind.PROVIDER_ACCEPT, EffectKind.PROVIDER_REJECT, EffectKind.PROVIDER_CANCEL}
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
    (ILLDirection.LENDING, WorkflowState.REQUESTED, WorkflowState.ACCEPTED): (
        EffectKind.PROVIDER_ACCEPT,
    ),
    (ILLDirection.LENDING, WorkflowState.REQUESTED, WorkflowState.REJECTED): (
        EffectKind.PROVIDER_REJECT,
    ),
    (ILLDirection.LENDING, WorkflowState.ACCEPTED, WorkflowState.ON_LOAN): (
        EffectKind.FOLIO_OPEN_LOAN,
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
            continue
        if effect_kind in _PROVIDER_EFFECTS:
            command = ProviderCommand(effect_kind.value)
            if not provider.writes_enabled or command not in provider.capabilities.commands:
                continue
        effects.append(effect_kind)

    return tuple(effects)
