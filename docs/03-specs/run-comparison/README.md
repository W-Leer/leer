# Run Comparison Specs

This folder defines the canonical run comparison design for Leer.

## Canonical document

- `01-run-comparison-spec.md`

## Purpose

Run comparison in Leer is a first-class debugging feature.

It should answer:

- what changed between two runs
- which steps truly correspond to each other
- which steps are missing on one side
- how LLM behavior changed in a structured, provider-aware way

## Principles

- truthful alignment over forced pairing
- exact name match before positional fallback
- provider-aware LLM compare is first-class
- generic step compare remains supported
- compare should feel as polished as run detail

## Notes

If implementation choices conflict with older compare assumptions, follow:

- `01-run-comparison-spec.md`
