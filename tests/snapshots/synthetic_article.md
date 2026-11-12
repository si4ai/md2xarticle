---
title: Pipeline Sketch
---

# Pipeline Sketch

A synthetic article used as a test fixture. Every name in it is made up.

## Overview

The pieces fit together like this:

```mermaid
flowchart LR
    Ingest[Source file] --> Parse[Parse blocks]
    Parse --> Render[Render diagram]
    Render --> Compose[Compose canvas]
    Compose --> Out[Output image]
```

## Decisions

Each request takes one of two paths:

```mermaid
flowchart TD
    Start([Request]) --> Check{Cached?}
    Check -->|yes| Serve[Serve copy]
    Check -->|no| Build[Build fresh]
    Build --> Store[Store result]
    Store --> Serve
```

A plain code block is not a diagram:

```python
print("not mermaid")
```

## Calls

```mermaid
sequenceDiagram
    participant App
    participant Renderer
    participant Composer
    App->>Renderer: render(source, theme)
    Renderer-->>App: image
    App->>Composer: compose(image, size)
    Composer-->>App: canvas
```

## Types

```mermaid
classDiagram
    class Shape {
        <<abstract>>
        +area() float
    }
    class Circle
    class Square
    Shape <|-- Circle
    Shape <|-- Square
```

## Broken on purpose

```mermaid
flowchart TD
    A[Start] --> B{Decision
    this line is broken on purpose
    C --> D
```

The end.
