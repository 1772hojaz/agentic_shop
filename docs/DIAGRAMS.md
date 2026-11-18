# Architecture diagram sources

The PNG diagrams in the repository root remain available for document exports.
The Mermaid sources below describe the implemented module boundaries.

## System architecture

```mermaid
flowchart TD
    Customer[Customer WhatsApp] --> Meta[Meta Cloud API]
    Admin[Administrator browser] --> Nginx[Nginx HTTPS]
    Meta --> Nginx
    Nginx --> API[FastAPI modular monolith]
    API --> Auth[Identity and permissions]
    API --> Commerce[Catalogue, stock, carts, orders, payments]
    API --> Agent[Single AI orchestrator]
    Agent --> Model[External model API]
    Agent --> Registry[Permission-aware tools]
    Registry --> Commerce
    Commerce --> Database[(PostgreSQL)]
    API --> Inbox[Durable inbox and outbox]
    Inbox --> Meta
    Commerce --> Stripe[Stripe hosted checkout]
```

## Single agent

```mermaid
flowchart TD
    Agent[Single AI agent / external model API]
    Agent --> Customer[Customer context]
    Agent --> Admin[Administrator context]
    Customer --> Registry[Identity, role, permission, parameters, confirmation]
    Admin --> Registry
    Registry --> Search[Product Search]
    Registry --> Inventory[Inventory Lookup]
    Registry --> Cart[Cart Management]
    Registry --> Order[Order Management]
    Registry --> Sales[Sales Reporting]
    Registry --> Customers[Customer Lookup]
    Registry --> Stock[Stock Adjustment]
    Registry --> Notice[Notifications]
    Search & Inventory & Cart & Order & Sales & Customers & Stock & Notice --> Services
    Services[Backend business services] --> DB[(Transactional PostgreSQL)]
```

## Use cases

```mermaid
flowchart LR
    Customer((Customer)) --> Discover[Discover products]
    Customer --> Cart[Manage own cart]
    Customer --> Checkout[Confirm checkout]
    Customer --> Pay[Pay through provider]
    Customer --> Track[Track own orders]
    Staff((Staff)) --> Fulfill[Manage permitted orders]
    Manager((Manager)) --> Fulfill
    Manager --> Stock[Confirm stock and price changes]
    Manager --> Reports[Read sales reports]
    Owner((Owner)) --> Reports
    Owner --> StaffAccess[Manage staff and permissions]
    Owner --> Settings[Confirm shop and agent configuration]
```

## Domain classes

```mermaid
classDiagram
    Customer "1" --> "1" Cart
    Cart "1" --> "*" CartItem
    Product "1" --> "*" Variant
    Variant "1" --> "1" Inventory
    Variant "1" --> "*" StockMovement
    CartItem "*" --> "1" Variant
    Customer "1" --> "*" Order
    Order "1" --> "*" OrderItem
    Order "1" --> "*" Payment
    Payment "1" --> "*" PaymentEvent
    class Order {
        UUID id
        Decimal total
        string status
        transition(target)
    }
    class Principal {
        UUID id
        string context
        set permissions
        require(permission)
    }
    Principal --> Confirmation
```

## Components

```mermaid
flowchart LR
    Routes[REST routes] --> Auth[Authentication]
    Routes --> Catalogue[Catalogue services]
    Routes --> Orders[Order services]
    Routes --> Reports[Reporting]
    Routes --> Registry[Tool registry]
    Agent[AI orchestration] --> Registry
    Registry --> Catalogue
    Registry --> Orders
    Registry --> Payments[Payment services]
    Webhooks[Signed webhook routes] --> Inbox[Inbox]
    Worker[Bounded worker] --> Inbox
    Worker --> Outbox[Outbox]
    Worker --> Agent
    Catalogue & Orders & Reports & Payments --> Database[(SQLAlchemy / PostgreSQL)]
```

## Deployment

```mermaid
flowchart TD
    Internet --> Host[Ubuntu host Nginx / TLS]
    subgraph VPS[Approximately 1 GB RAM target]
        Host --> Web[Static React / Nginx container, 64 MB cap]
        Web --> API[FastAPI, one Uvicorn worker, 320 MB cap]
        API --> DB[(PostgreSQL, 256 MB cap)]
        API --> Uploads[(Persistent upload volume)]
        Backup[Scheduled backup script] --> DB
        Backup --> Uploads
    end
    API --> Model[External model]
    API --> Meta[Meta Cloud API]
    API --> Stripe[Stripe]
```

## Customer shopping sequence

```mermaid
sequenceDiagram
    actor Customer
    participant Meta
    participant API
    participant Worker
    participant Agent
    participant Services
    Customer->>Meta: Search, choose variant, update cart
    Meta->>API: Signed event with unique message ID
    API->>API: Verify and persist inbox job
    API-->>Meta: Acknowledge durable receipt
    Worker->>Agent: Load verified customer context
    Agent->>Services: Permission-checked tool call
    Services-->>Agent: Authoritative result
    Agent-->>Worker: Response and pending actions
    Worker->>Meta: Send response through outbox
    Customer->>Meta: CONFIRM checkout-ID
    Worker->>Services: Consume exact customer confirmation
    Services->>Services: Reserve stock and create unpaid order
```

## Administrator sequence

```mermaid
sequenceDiagram
    actor Admin
    participant Web
    participant API
    participant Meta
    participant Registry
    Admin->>Web: Sign in with password
    Web->>API: Generate one-time pairing code
    API-->>Web: Code valid for five minutes
    Admin->>Meta: PAIR code
    Meta->>API: Signed sender event
    API->>API: Bind sender for one hour
    Admin->>Meta: Add 15 stock units
    API->>Registry: Resolve current permissions and validate
    Registry-->>Admin: Exact pending action ID
    Admin->>Meta: CONFIRM action-ID
    Registry->>Registry: Recheck permission, claim once, execute
```

## Tool calling sequence

```mermaid
sequenceDiagram
    participant Agent
    participant Model
    participant Registry
    participant Services
    participant DB
    Agent->>Model: Scoped history and allowed tool schemas
    Model-->>Agent: Tool name and arguments
    Agent->>Registry: Verified principal plus requested arguments
    Registry->>Registry: Strict schema and permission checks
    alt Sensitive operation
        Registry->>DB: Store exact pending confirmation
        Registry-->>Agent: Human confirmation required
    else Permitted read or personal cart operation
        Registry->>Services: Execute validated business operation
        Services->>DB: Query or transaction
        DB-->>Agent: Authoritative result through services
    end
    Agent->>Model: Tool result
    Model-->>Agent: Response text
```

## Order lifecycle activity

```mermaid
flowchart TD
    Cart[Personal cart] --> Validate[Validate live prices and stock]
    Validate --> Reserve[Atomically reserve stock]
    Reserve --> Unpaid[Create unpaid order and snapshots]
    Unpaid --> Method{Payment method}
    Method -->|Stripe| Init[Persist initializing payment]
    Init --> Provider[Worker creates hosted checkout]
    Provider --> Verify[Verify signed matching settlement]
    Verify --> Paid[Record paid state]
    Method -->|Cash| Cash[Record unpaid cash arrangement]
    Cash --> Fulfill[Fulfillment processing]
    Paid --> Fulfill
    Fulfill --> Receipt[Verify settlement before completion]
    Receipt --> Complete[Complete order]
    Unpaid -->|Cancellation or expiry| Release[Release reserved stock]
```

## Order state machine

```mermaid
stateDiagram-v2
    [*] --> pending_payment
    pending_payment --> paid: verified settlement
    pending_payment --> processing: explicit unpaid cash arrangement
    pending_payment --> cancelled
    pending_payment --> expired
    paid --> processing
    paid --> refund_pending
    processing --> ready_for_delivery
    processing --> cancelled: unpaid only
    processing --> refund_pending: settled only
    ready_for_delivery --> out_for_delivery
    ready_for_delivery --> completed: settled collection
    ready_for_delivery --> cancelled: unpaid only
    ready_for_delivery --> refund_pending: settled only
    out_for_delivery --> delivered
    out_for_delivery --> delivery_failed
    out_for_delivery --> cancelled: unpaid only
    delivery_failed --> out_for_delivery
    delivery_failed --> cancelled: unpaid only
    delivery_failed --> refund_pending: settled only
    delivered --> completed: settled only
    delivered --> refund_pending
    completed --> refund_pending
    cancelled --> refund_pending: late settlement exception
    expired --> refund_pending: late settlement exception
    refund_pending --> refunded: verified provider result
```

## Entity relationships

```mermaid
erDiagram
    users ||--o{ user_roles : assigned
    roles ||--o{ user_roles : includes
    roles ||--o{ role_permissions : grants
    permissions ||--o{ role_permissions : identifies
    users ||--o{ auth_sessions : authenticates
    users ||--o{ admin_bindings : pairs
    categories ||--o{ products : groups
    products ||--|{ product_variants : offers
    product_variants ||--|| inventory : stocks
    product_variants ||--o{ stock_movements : tracks
    customers ||--o| carts : owns
    carts ||--o{ cart_items : contains
    product_variants ||--o{ cart_items : selects
    customers ||--o{ orders : places
    orders ||--|{ order_items : snapshots
    orders ||--o{ payments : attempts
    payments ||--o{ payment_events : verifies
    conversations ||--o{ messages : contains
    conversations ||--o| agent_sessions : summarizes
    conversations ||--o{ ai_usage : measures
```
