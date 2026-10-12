-- Add RENEWAL_REQUESTED and RENEWAL_ACKNOWLEDGED to the allowed
-- ill_requests.workflow_state values so the check constraint matches
-- ill_bridge.common.states.WorkflowState.

ALTER TABLE ill_requests
    DROP CONSTRAINT IF EXISTS ill_requests_workflow_state_check;

ALTER TABLE ill_requests
    ADD CONSTRAINT ill_requests_workflow_state_check
    CHECK (
        workflow_state IN (
            'REQUESTED',
            'ACKNOWLEDGED',
            'RESERVED',
            'DELIVERED',
            'RENEWAL_REQUESTED',
            'RENEWAL_ACKNOWLEDGED',
            'ACCEPTED',
            'ON_HOLD',
            'IN_TRANSIT',
            'RECEIVED',
            'READY_FOR_PICKUP',
            'ON_LOAN',
            'RETURN_PENDING',
            'RETURN_IN_TRANSIT',
            'RETURNED',
            'FULFILLED',
            'COMPLETED',
            'CANCEL_PENDING',
            'CANCELLED',
            'REJECTED',
            'EXPIRED'
        )
    );
