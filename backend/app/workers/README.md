# Workers

Workers run long-lived or repeatable jobs outside normal HTTP requests.

Planned responsibilities:

- Execute and monitor the date-level collection jobs created by the collection service.
- Persist crawl run status, row counts, parser errors, and retry metadata.
- Execute platform mutations only after preview, confirmation, idempotency, and audit are implemented.

FastAPI routes should trigger or inspect worker state, not perform crawling or batch platform work inline.
