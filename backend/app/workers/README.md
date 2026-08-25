# Workers

Workers run long-lived or repeatable jobs outside normal HTTP requests.

Planned responsibilities:

- Build daily import request plans from the contract catalog.
- Run dry-run previews before any platform replay is enabled.
- Persist import run status, row counts, parser errors, and retry metadata.
- Execute platform mutations only after preview, confirmation, idempotency, and audit are implemented.

FastAPI routes should trigger or inspect worker state, not perform crawling or batch platform work inline.

