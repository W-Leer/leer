# Leer — Provider-aware UI Spec

## Purpose

Render LLM steps with richer UI based on provider-aware data.

Fallback to generic UI if unavailable.

---

## Layout

### Header

- Provider
- Model
- Duration
- Tokens

---

## Sections

### 1. Prompt / Messages

- render messages with roles
- preserve formatting

### 2. Response

- show main text
- support structured blocks

### 3. Tool Calls

- list tool calls if present

### 4. Usage

- prompt / completion / total tokens

### 5. Error

- show error clearly

### 6. Raw toggle

- show raw artifacts

---

## Principles

- calm UI
- readable first, raw second
- consistent across providers

---

## Compare Page

Use normalized data for diff:

- model differences
- prompt differences
- response differences

---

## Fallback

If no provider data:

- show generic Input / Output / Error

