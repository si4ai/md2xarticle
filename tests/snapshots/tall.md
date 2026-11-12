---
title: Order Service
subtitle: A synthetic set of tall diagrams
---

# Order Service

A synthetic fixture: tall diagrams that are limited by the height of a 16:9
canvas, and a dense gitGraph. Every name in it is made up.

## Request path

```mermaid
flowchart TD
    Client[Client app] --> Edge[Edge proxy]
    subgraph Gateway
        Edge --> Auth{Token valid?}
        Auth -->|no| Deny[Reject with 401]
        Auth -->|yes| Limit[Rate limiter]
    end
    subgraph Orders
        Limit --> Router[Order router]
        Router --> Validate[Validate cart]
        Validate --> Price[Price items]
        Price --> Reserve[Reserve stock]
    end
    Reserve --> Queue[(Work queue)]
    Queue --> Worker[Fulfilment worker]
    Worker --> Done([Order placed])
```

## Checkout calls

```mermaid
sequenceDiagram
    participant User
    participant Web
    participant Orders
    participant Payments
    User->>Web: open checkout
    Web->>Orders: load cart
    Orders-->>Web: cart lines
    Web-->>User: show totals
    User->>Web: confirm order
    Web->>Orders: create order
    Orders->>Payments: authorize card
    Payments-->>Orders: approved
    Note over Orders,Payments: retried twice on timeout
    Orders->>Orders: reserve stock
    Orders-->>Web: order id
    Web-->>User: confirmation page
    loop every 30 s
        Web->>Orders: poll status
        Orders-->>Web: shipped?
    end
```

## Release history

```mermaid
gitGraph
    commit id: "init"
    commit id: "add schema"
    branch feature
    commit id: "add parser"
    commit id: "add tests"
    checkout main
    commit id: "fix typo"
    branch hotfix
    commit id: "patch timeout"
    checkout main
    merge hotfix id: "merge hotfix"
    merge feature id: "merge feature" tag: "v1.0"
    commit id: "release notes"
```

## Team flow

A subgraph with an outgoing edge and an incoming back edge, the shape that
makes the default layout leave empty space at the bottom of the box.

```mermaid
flowchart TD
    subgraph Teams[Team desks working in parallel]
        T1[Research desk]
        T2[Build desk]
        T3[Review desk]
    end
    Teams -->|hand off| Queue[Shared queue of proposals]
    Queue -->|proposals| Gate{Release gate and checks}
    subgraph Live[Live systems behind the gate]
        L1[Public API]
        L2[Main branch]
        L3[Billing data]
    end
    subgraph Tools[Working area]
        W1[Telemetry]
        W2[Helper scripts]
        W3[Scratch notes]
    end
    Gate -->|approve| Live
    Gate -->|tidy| Tools
    Gate -.->|record| Notes[Decision log]
    Notes -.->|informs| Teams
```
