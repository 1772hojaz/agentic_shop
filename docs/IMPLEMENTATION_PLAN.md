# Implementation plan

## Architecture and delivery order

Implement the eight phases in PROMPT.txt in dependency order: foundation,
commerce, administration, WhatsApp, AI, payments, security, and deployment.
Use a modular FastAPI monolith, SQLAlchemy transactions, PostgreSQL, and a
React/TypeScript administration client. Nginx serves the compiled client and
proxies the API. One Uvicorn worker, a small database pool, and a database-backed
outbox avoid Redis, worker fleets, and local models on the 1 GB target.

This checkout targets the requested Ubuntu deployment, not Sites hosting.

## Data relationships

Users have roles through user_roles; roles have permissions through
role_permissions. Revocable, hashed sessions authenticate requests. Customers
own carts, orders, conversations, and messages. Products belong to categories,
have variants, and each variant has inventory and stock movements. Order items
snapshot product descriptions and prices. Orders have independent payments and
unique provider events. Conversations have agent sessions and usage records.
Notifications and webhook deliveries are persisted for bounded retries. Audit
records identify the actor, operation, entity, and time. Confirmation records
bind a specific actor, operation, payload digest, expiry, and single use.

Use Decimal money, UTC timestamps, foreign keys, unique event references,
positive-quantity constraints, and atomic stock deductions. Lock order rows for
state transitions and payment rows for callbacks. Never infer payment success
from checkout or unverified model output.

## Module boundaries and API contracts

- core: validated environment, database unit of work, errors and logging.
- auth: password hashing, session cookies/bearer tokens, role permissions,
  login throttling, and a short-lived WhatsApp administrator pairing code.
- catalogue: paginated products/categories, variants and image uploads.
- commerce: personal carts, stock movements, order state machine and payments.
- operations: customers, reports, staff, settings, audits and notifications.
- integrations: signed Meta webhooks, outgoing messages and payment adapter.
- agent: external model client, scoped history, usage accounting and registry.
- frontend: authenticated routes sharing typed HTTP calls and accessible forms.

Routes use /api/v1, JSON request/response bodies, UUID identifiers, bounded
pagination, explicit permissions, and structured error responses. Authentication
accepts a secure HttpOnly same-site cookie or bearer session token. Cookie writes
require the matching CSRF header. Public catalogue reads expose no private data.
Customer records are never selected using model-supplied identity: the backend
injects the authenticated owner. The API's generated /docs and /openapi.json are
the authoritative contracts.

## Agent and WhatsApp workflow

Verify Meta's raw-body HMAC, persist each incoming message once, acknowledge,
and process from a durable inbox. Identify customers by verified Meta sender.
Administrators pair their WhatsApp sender using a one-time code created from an
authenticated web session; bindings expire. Phone number registration alone
does not grant admin access. The same agent selects context and permitted tool
definitions from backend identity. Each call validates a strict schema and
permission, then invokes shared business services. Sensitive requests create a
pending confirmation; only an explicit subsequent human action consumes it.
Model arguments cannot supply confirmation consent. Bound history, tools,
request timeouts and output tokens; persist actual token usage and configured
price estimates. No model key or raw credential leaves the server.

## External dependencies and risks

Meta requires a configured business account, phone-number ID, access token,
app secret, verification token, supported Graph API version and HTTPS endpoint.
The model integration requires an OpenAI-compatible HTTPS chat-completions API
and configured model. Stripe is the initial real online payment adapter; cash
on delivery/collection is explicitly unpaid until an authorised staff action.
Other mobile-money providers require a provider-specific adapter and credentials;
they must not be advertised as working integrations. Signature verification,
idempotency and amount/currency matching precede payment state changes.

Concurrent purchases, duplicate callbacks, privilege escalation, prompt
injection, retries, abandoned stock reservations, provider outages, and secret
exposure are primary risks. Cover them with service/API tests, fail-closed
configuration, transactions, immutable confirmations and bounded retries.
SQLite is permitted only for fast development tests: PostgreSQL integration
tests remain necessary for production concurrency guarantees.

## Coding conventions

Betty is a C style checker and does not validate Python or TypeScript. Apply
its relevant rules here: small single-purpose functions, descriptive names,
documented functions/classes, no trailing whitespace, no multiple statements
per line, explicit blocks, and consistent formatting. Python uses four spaces,
79-column lines and Ruff checks; TypeScript uses two spaces and Prettier.
Do not mislabel a Python/TypeScript formatter as the Betty C checker.

## Deployment and verification

Provide Alembic migrations, an interactive owner bootstrap, environment
examples, Docker Compose, Nginx, TLS instructions, rotating JSON logs,
health/readiness endpoints and a scheduled database backup/restore runbook.
Build the frontend outside the VPS if memory is insufficient. No secrets or
default production passwords are committed. Validate backend authorization,
customer isolation, confirmations, stock rollback, order/payment transitions,
webhook replay and provider failures; compile/typecheck the client and inspect
the rendered dashboard when the local preview is available.

Production activation needs real credentials and HTTPS. Local verification
must report these boundaries rather than substitute fake integrations.
