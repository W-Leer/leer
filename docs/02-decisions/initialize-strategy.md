# Leer.initialize() Strategy

## Goal
One-line setup WITHOUT losing control.

## API

```python
Leer.initialize(
    api_key="...",
    project="...",
    integrations=["openai"],
    auto_instrument=False,
)
```

## Layers

### 1. Explicit (Core)
- @trace
- step()
- tool_step()

### 2. Initialize (Config)
- setup
- batching
- lifecycle hooks

### 3. Integrations
- instrument_openai()
- instrument_anthropic()

### 4. Optional Auto Mode
- disabled by default
- explicit opt-in

## Rules
- No hidden monkey patching by default
- Everything inspectable
- Integrations modular
- Explicit APIs always available

## Philosophy
Convenience WITHOUT magic.
