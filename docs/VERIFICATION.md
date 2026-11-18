# Verification record

Local verification on Windows, 17 November 2026:

| Check | Result |
| --- | --- |
| Backend regression suite | 32 passed, 1 skipped. |
| PostgreSQL concurrent checkout test | Skipped locally; Docker daemon unavailable. Configured to run against a disposable PostgreSQL service in CI. |
| Ruff | Application, tests, migrations, and style checker pass. |
| Python structural style | All application definitions documented; every application function is at most 40 lines. |
| Prettier | Frontend source formatting checked. |
| TypeScript / Vite | Production build verified; chart and workspace modules split into lazy chunks. |
| Alembic | Upgrade, downgrade to base, upgrade again, and metadata drift check passed on isolated SQLite storage. |
| Docker Compose | Configuration validated against the example environment; containers were not started. |
| Live local HTTP | Frontend response, proxy to backend, password login, authenticated inventory, CSRF-protected logout, and session revocation passed against an isolated QA database. |
| Browser layout review | Not performed: browser automation's native connection was unavailable. |
| Live external integrations | Not exercised: Meta, model, and Stripe credentials are not supplied. |
| Ubuntu / 1 GB capacity | Deployment configuration provided; runtime memory and load behavior are not measured here. |

The regression suite covers customer data isolation, strict tool arguments,
role checks, CSRF, session expiry/revocation, login throttling, exact single-use
confirmation, stock rollback across multiple line items, idempotent checkout,
price snapshots, cash fulfillment/receipt, signed event replay, amount checks,
durable payment initialization, refund state preservation, administrator
pairing, measured model usage, retained token accounting at budget exhaustion,
unconfigured provider failures and image validation.

Provider responses are substituted only in isolated test cases. Application
code uses real external HTTP contracts and fails closed when required values
are missing. A provider configuration flag is not proof of a working account.
CI is supplied but has not been run remotely in this session.

Betty's executable checks C. Python and TypeScript use language-appropriate
formatters and checks; no claim is made that the C checker validates them.
The Python structural checker applies its relevant small-function and
documentation principles. Generated Alembic schema functions are exempt from
the application function-size rule.
