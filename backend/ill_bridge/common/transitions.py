from __future__ import annotations

from dataclasses import dataclass

from ill_bridge.common.exceptions import InvalidWorkflowTransition
from ill_bridge.common.states import WorkflowState

WORKFLOW_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.REQUESTED: frozenset({
        WorkflowState.ACCEPTED,
        WorkflowState.ACKNOWLEDGED,
        WorkflowState.REJECTED,
        WorkflowState.ON_HOLD,
        WorkflowState.EXPIRED,
        WorkflowState.CANCELLED,
    }),
    
    WorkflowState.ACKNOWLEDGED: frozenset({
        WorkflowState.RESERVED,
        WorkflowState.CANCELLED,
    }),
    
    WorkflowState.RESERVED: frozenset({
        WorkflowState.IN_TRANSIT,
        WorkflowState.CANCELLED,
    }),

    WorkflowState.ACCEPTED: frozenset({
        WorkflowState.IN_TRANSIT,
        WorkflowState.CANCELLED,
    }),

    WorkflowState.ON_HOLD: frozenset({
        WorkflowState.ACCEPTED,
        WorkflowState.REJECTED,
        WorkflowState.CANCELLED,
    }),

    WorkflowState.IN_TRANSIT: frozenset({
        WorkflowState.ARRIVED,
        WorkflowState.RECEIVED,
    }),

    WorkflowState.ARRIVED: frozenset({
        WorkflowState.RECEIVED,
        WorkflowState.RETURNED_FROM_PATRON,
    }),

    WorkflowState.RECEIVED: frozenset({
        WorkflowState.ON_LOAN,
        WorkflowState.RENEWAL_REQUESTED,
        WorkflowState.RETURNED_FROM_PATRON,
    }),
    
    WorkflowState.RENEWAL_REQUESTED: frozenset({
        WorkflowState.RETURNED_FROM_PATRON,
    }),

    WorkflowState.RETURNED_FROM_PATRON: frozenset({
        WorkflowState.RETURN_IN_TRANSIT,
    }),
    
    WorkflowState.READY_FOR_PICKUP: frozenset({
        WorkflowState.ON_LOAN,
        WorkflowState.RETURN_PENDING,
    }),

    WorkflowState.ON_LOAN: frozenset({
        WorkflowState.RETURN_PENDING,
    }),

    WorkflowState.RETURN_PENDING: frozenset({
        WorkflowState.RETURN_IN_TRANSIT,
    }),

    WorkflowState.RETURN_IN_TRANSIT: frozenset({
        WorkflowState.RETURNED,
        WorkflowState.RETURNED_FROM_PATRON, # For undo
    }),

    WorkflowState.RETURNED: frozenset({
        WorkflowState.COMPLETED,
    }),
}

@dataclass(frozen=True)
class Workflow:
    state: WorkflowState

    def can_transition_to(self, target: WorkflowState) -> bool:
        return target in WORKFLOW_TRANSITIONS.get(
            self.state,
            frozenset(),
        )

    def transition_to(self, target: WorkflowState) -> "Workflow":
        if not self.can_transition_to(target):
            raise InvalidWorkflowTransition(f"{self.state} -> {target}")

        return Workflow(state=target)
