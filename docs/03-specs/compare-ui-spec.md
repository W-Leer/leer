# Compare UI Spec

This document defines the UI for run comparison.

---

## Goal

The compare view should let a user instantly see:

- what changed between two runs
- which step failed
- which outputs differ

The UI must prioritize clarity over complexity.

---

## Layout

### Header

Show:

- "Compare Runs"
- Run A status + timestamp
- Run B status + timestamp

---

## Step Comparison

Each step is displayed as a block.

### Step header

- sequence index
- step name
- step type

Example:

Step 1 — llm_call (llm)

---

## Fields to display

### Status

Show:

A: completed  
B: failed  

Highlight if different.

---

### Output Summary

Show:

A: output_summary  
B: output_summary  

Highlight if different.

---

### Error Summary

Show only if present.

A: error_summary  
B: error_summary  

Highlight if different.

---

## Highlighting

- use color to indicate differences
- red for errors or failures
- neutral for identical values

---

## Ordering

Steps must be displayed in ascending sequence_index.

---

## Rules

- always show all steps
- do not hide unchanged steps
- do not use complex diff visualization
- keep layout vertical
- keep UI minimal

---

## Non-goals

- no inline text diff
- no syntax highlighting
- no side-by-side layout
- no advanced filtering