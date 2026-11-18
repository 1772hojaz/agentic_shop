# Run and deploy Agentic Shop

## Local development

Requirements: Python 3.10+, Node.js 22, and npm. PostgreSQL 16 is recommended;
SQLite is provided for local development and fast tests only.

From the repository root on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.cli create-owner --email owner@example.com
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173 and sign in with the owner account you created.
There are no seeded production credentials or fabricated dashboard statistics.
The Vite proxy keeps cookies and API requests on one origin. The API schema is
available at http://127.0.0.1:8000/docs. Run backend commands from `backend/`
so the environment file, database, and uploads resolve consistently.

Linux uses `.venv/bin/python` in place of `.venv\Scripts\python.exe`.
To use PostgreSQL locally, set `DATABASE_URL` to a
`postgresql+psycopg://user:password@localhost:5432/agentic_shop` URL before
running migrations. URL-encode special characters in database passwords.

## Real integrations

Configure credentials in `backend/.env` locally or the root `.env` for Compose.
Never commit these files. Configuration flags only report whether values are
present; a successful provider call is needed to validate credentials.

### External model

Set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` for an OpenAI-compatible
chat-completions API that supports function tools and `max_completion_tokens`.
The default URL targets OpenAI; other providers must support this contract.
Do not point it at a local model on the low-memory VPS. Owners can change the
model, token budget, iteration limit and per-million-token prices through the
dashboard. Prices are operator configuration, not automatically fetched prices.
A zero price means usage is tracked but estimated spend remains zero.

### WhatsApp Cloud API

1. Configure a Meta business app and its WhatsApp phone number.
2. Set `META_ACCESS_TOKEN`, `META_PHONE_ID`, `META_APP_SECRET`,
   `META_VERIFY_TOKEN`, and a currently supported `META_GRAPH_VERSION`.
3. Register `https://your-host/webhooks/whatsapp` as the callback. Use the same
   verification token and subscribe to message events.
4. Complete Meta's business, recipient and app-mode requirements.
5. Send a real customer message and inspect inbox/outbox delivery state.

Messages are deduplicated in a durable inbox. One in-process worker consumes
them and an outbox with at most five delivery attempts. At-least-once outbound
delivery can produce duplicates if Meta accepts a message but the network
fails before acknowledgement. This is explicitly not an exactly-once transport.
Free-form messages require the applicable WhatsApp customer-service window.
For business-initiated messages outside that window use an approved template.
The notification API supports text, HTTPS image/document links, interactive
support buttons and approved parameterless templates. Templates with variable
parameters require extending the strict template contract before use.
Incoming image/document captions and metadata are accepted; attachment contents
are not downloaded or interpreted by the text agent.

Administrators sign in on the web, generate a pairing code, then send
`PAIR <code>` through WhatsApp. The one-use code expires after five minutes;
the pairing lasts one hour. `UNPAIR` or web logout ends access. A phone number
alone grants no administrative capability. Sensitive operations return a
confirmation ID. The human sends `CONFIRM <id>` or approves its exact payload
on the dashboard; the model cannot approve operations itself.

### Payments

Stripe hosted checkout and cash receipt are implemented. Set
`STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`; register
`https://your-host/webhooks/payments` for:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`
- `refund.created`, `refund.updated`, `refund.failed`

Start with Stripe test credentials and its signed test events. Checkout creates
an unpaid order. Stripe initialization is a durable background operation:
the initial payment response has `status: initializing`; poll the payment API
or ask the agent for status. The worker stores the real checkout URL and queues
it to the customer. A verified, matching callback establishes payment success.
Stable payment IDs and provider idempotency keys protect initialization retries.
Cash payment initiation only records instructions; authorised staff must confirm
actual receipt. Cash fulfillment can proceed unpaid, but completion requires
settlement. Online refunds require a settled Stripe payment and a
`refund_pending` order; failed refunds stay visible for operator review.

Initial currency minor-unit rules cover USD, EUR, GBP and RWF. Extend the
explicit rules before enabling another Stripe currency. Currency is fixed per
deployment to avoid mixing unlike currencies in aggregate reports. Mobile-money
and bank-transfer providers are not represented as working integrations:
add a provider adapter and signed settlement contract for your operating market.

## Ubuntu production deployment

1. Install Docker Engine with Compose, host Nginx, and Certbot. Point your DNS
   hostname to the VPS. Restrict public ingress to SSH, HTTP, and HTTPS.
2. Copy `.env.example` to `.env`. Choose a unique database password and matching
   `DATABASE_URL`; set the real HTTPS `PUBLIC_URL`, `ENVIRONMENT=production`,
   and `COOKIE_SECURE=true`. Protect the file with `chmod 600 .env`.
3. Build images on a development machine or CI when the VPS cannot spare build
   memory. Transfer those images, or build with adequate temporary memory.
4. Run `docker compose up -d --build`. The API applies Alembic migrations before
   starting. Named volumes retain PostgreSQL and product uploads.
5. Run `docker compose exec api python -m app.cli create-owner --email <email>`.
6. Obtain a certificate using Certbot, replace the hostname in
   `deploy/nginx-https.conf`, install that host Nginx configuration, and verify
   `nginx -t` before reloading. Enable automatic certificate renewal.
7. Confirm `/health`, `/ready`, HTTPS login, webhook delivery and a real
   provider test checkout before accepting customers.

Only the web container binds a host port, on `127.0.0.1:8080`. PostgreSQL and
the API have no public ports. The trusted host Nginx overwrites client IP
headers; the inner Nginx forwards those to the unexposed Uvicorn service.
Do not expose the internal API directly with its trusted proxy configuration.

Compose caps database/API/web memory at 256/320/64 MB. These are starting
limits, not a measured capacity guarantee. Allow memory for Ubuntu, Docker,
host Nginx, backups and filesystem cache. Use one Uvicorn worker, a three-slot
database pool, five maximum connections, and conservative PostgreSQL memory.
Load-test the actual VPS with realistic conversations before increasing limits.

## Backups and recovery

Run `sh deploy/backup.sh` daily, for example through a dedicated user's cron:

```cron
15 2 * * * cd /srv/agentic_shop && sh deploy/backup.sh
```

Copy encrypted backups off the VPS and apply a retention policy. The script
creates a custom-format database dump and upload archive with restrictive
permissions. It intentionally does not silently delete previous backups.
Back up `.env` separately using a secure secret store.

To restore, stop incoming traffic and the API, retain a backup of the current
state, restore into a clean database, then restore uploads:

```sh
docker compose stop web api
cat backups/database-TIMESTAMP.dump | docker compose exec -T db sh -c \
  'pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose run --rm -T --no-deps api tar xzf - -C /app \
  < backups/uploads-TIMESTAMP.tar.gz
docker compose up -d
```

Test restores regularly on an isolated database. Never run destructive restore
commands against the only copy of a live database. Deploy additive migrations
first; take backups before upgrades and assess migration reversibility before
rolling back application images.

## Operations and verification

- `sh deploy/monitor.sh`: host memory, disk and container resource snapshots.
- `docker compose logs --tail=100 api`: structured HTTP timings/statuses and
  integration failures. Compose rotates log files.
- Dashboard: AI token usage/spend, pending confirmations, audit history,
  notification delivery and failed integration jobs.
- `/health` is liveness; `/ready` checks connectivity and migration metadata.
- Review failed deliveries and reconcile late/duplicate settlements before
  retrying sensitive operations. Refunds do not automatically restock returned
  goods; staff record a separate confirmed stock adjustment after inspection.
- Set a retention policy appropriate to the business. Remove expired sessions,
  used pairing codes, processed inbox payloads and aged conversation records
  through a reviewed database maintenance job; retain legally required business
  and payment audit records.

Backend checks (from `backend/`):

```sh
python -m ruff check app tests migrations
python -m ruff format --check app tests migrations
python check_style.py
python -m pytest -q
python -m alembic upgrade head
python -m alembic check
```

Frontend checks (from `frontend/`): `npm run format:check` and `npm run build`.
The Python structural check enforces documented definitions and functions of
at most 40 lines. Ruff and Prettier implement language-appropriate formatting;
the C-specific Betty executable cannot validate Python or TypeScript.
Tests substitute provider responses only inside the test suite; production
integrations never return fabricated success responses.
