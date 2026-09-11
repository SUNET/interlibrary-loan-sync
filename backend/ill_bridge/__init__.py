"""Provider-agnostic ILL (fjärrlån) integration service.

Bridges FOLIO and external ILL networks, starting with Libris.

Module boundaries (architecture proposal §5.3):

    api/            commands, queries, webhook ingress, authorization
    domain/         canonical models, transitions, guards, invariants
    application/    intake, provisioning, lending, cancellation, resync
    providers/      ILLProviderInterface, registry, per-provider adapters
    folio/          auth, inventory, circulation, users, observation
    persistence/    models, repositories, migrations, tenant policies
    jobs/           scheduler, dispatcher, tasks, reconciliation
    observability/  redaction, metrics, tracing

Provider adapters must never import from `folio`; the application layer
coordinates both sides.
"""

__version__ = "0.1.0"
