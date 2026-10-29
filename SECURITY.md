# Security Policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/W-Leer/leer/security/advisories/new),
not as public issues.

Include what you found, how to reproduce it, and its impact. You'll get
an acknowledgement as soon as possible.

## Scope and deployment notes

Leer is currently meant to run locally or on a trusted network:

- **The API has no authentication.** Anyone who can reach it can ingest
  and read runs. Don't expose it to the public internet.
- **Execution records may contain sensitive data.** Prompts, model
  outputs, tool inputs and outputs, and files are stored as captured. Treat
  the database and blob storage like application logs that may contain
  secrets or personal data.

Reports that rely only on exposing the unauthenticated API publicly are
known limitations, not vulnerabilities, but hardening suggestions are
welcome.
