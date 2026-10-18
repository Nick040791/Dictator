# Security Policy

## Supported versions

Currently, only the latest commit on the `stable` branch is actively
supported for security updates.

## Reporting a vulnerability

If you discover a security vulnerability in Dictator:

1. **Do not open a public GitHub issue.** This prevents exploitation before a
   fix is available.
2. Email the maintainer: `nick@beighley.net` (or use GitHub's [private security
   reporting](https://docs.github.com/en/code-security/security-advisories/)
   if available for this repository).
3. Provide a clear description, reproduction steps, and any proof of concept
   if applicable.

## What to expect

- **Acknowledgement:** within 2 business days (best effort).
- **Investigation:** we will triage the report and determine impact.
- **Remediation:** a fix will be prepared and disclosed responsibly. When
  appropriate, a patched release will be tagged on `stable`.

## Notes on scope

Dictator is a local, single-user desktop tool. Report issues that could affect
confidentiality, integrity, or availability of a user's system (e.g. command
injection in scripts, unsafe temp file handling, privilege escalation). Issues
that require physical access or exploiting misconfigured host systems are
generally out of scope.
