# API, schema and security boundaries

The generated `/docs` and `/openapi.json` expose all request contracts.
Versioned business routes live under `/api/v1`; provider callbacks live under
`/webhooks`. List endpoints use bounded `offset` and `limit` where applicable.
Decimal amounts serialize as precise decimal strings. IDs are UUID strings.
Times are UTC; the frontend displays them in the operator's local timezone.

## Identity

`POST /api/v1/auth/login` accepts email/password and sets a same-site HttpOnly
cookie. Its response supplies a CSRF token that clients send in
`X-CSRF-Token` for cookie-authenticated writes. `GET /auth/me` retrieves the
current identity and permissions; `POST /auth/logout` revokes the session and
WhatsApp pairing. Passwords use salted scrypt; sessions and one-time pairing
codes are stored only as SHA-256 digests. Bearer tokens are supported for
trusted clients, but the browser uses no localStorage authentication token.
There is no public staff registration or production default password.

Owner, manager and staff are seeded roles. Owners retain all permissions and
can assign operational grants to other roles. A staff account's permissions
are read from the database on every request; roles are not trusted token claims.
Disabled accounts immediately lose access. Customers are resolved from
verified Meta senders and access personal data through owner-scoped tools.
No customer ID supplied by a language model becomes an authorization identity.

## Exact confirmations

Price changes, stock adjustments, fulfillment changes, outbound notices,
settings, agent configuration, cash settlement and refunds produce a pending
confirmation. Agent-created checkout also requires confirmation. The record
contains the actor, exact validated payload and a five-minute expiry.
`POST /confirmations/{id}/confirm` consumes it atomically and rechecks current
permissions. The endpoint accepts no replacement business payload. A failed
business operation rolls back the confirmation claim. The model cannot invoke
this endpoint through the tool registry. Staff registration and role assignment
are owner-only direct web operations.

## Commerce integrity

Products reference categories; variants reference products and own one stock
balance. Stock movements record every adjustment and reservation. A customer
owns one cart; its items reference variants. Checkout locks the cart, validates
availability, atomically deducts stock, snapshots each line price/name, and
creates an unpaid order under a unique checkout key. Failed checkout rolls back
all deductions. Cancelling or expiring an unpaid order releases stock once.

Orders have payment attempts and verified payment events. Pending checkout,
redirects and model statements never establish settlement. Signed Stripe events
must match the stored provider session, amount and currency. Late payments for
released reservations become refund work rather than silently reclaiming stock.
Payment initialization is durable before an external API call. Refund state
is distinct from original settlement and is updated by verified refund events.

## Integration isolation

Meta HMAC and Stripe signatures are verified against raw request bytes before
processing. Unique incoming message/event references provide replay protection.
The database inbox/outbox persists jobs, caps retries and surfaces failures.
The external model has strict tool schemas and a permission-filtered registry.
Every requested operation is revalidated by the backend; prompt instructions
alone are not a security boundary. History, output, tool calls and daily usage
are bounded. Cost estimates use operator-supplied per-million-token rates.

The deployment uses HTTPS, request-size caps, bounded per-host rate limiting,
persisted login throttling, secure cookies, security headers, image decoding
and re-encoding, and ORM-bound parameters. The limiter is designed for the
documented single-worker deployment. A shared limiter and revised job ownership
are necessary before scaling to multiple application instances.

## Important limits

- SQLite checks do not establish PostgreSQL row-lock correctness.
- External credentials and business approval are required for live integrations.
- Refunds do not imply physical goods have been returned or restocked.
- Outbound Meta delivery is at least once; ambiguous network failures can
  duplicate a notification.
- Incoming attachment content is not inspected; only text/caption metadata
  enters the text agent.
- Parameterized Meta templates and market-specific mobile-money/bank adapters
  need additional provider contracts and tests.
- Capacity on a 1 GB VPS must be measured under the intended workload.

## Primary implementation references

- [FastAPI authentication guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [SQLAlchemy transaction boundaries](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [SQLAlchemy row locking](https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.Select.with_for_update)
- [Meta webhook verification](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/)
- [Stripe checkout sessions](https://docs.stripe.com/api/checkout/sessions/create)
- [OpenAI tool integration](https://developers.openai.com/api/docs/guides/tools)
