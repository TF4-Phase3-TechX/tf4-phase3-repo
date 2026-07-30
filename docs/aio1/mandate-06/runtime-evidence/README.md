# Mandate 06 committed runtime metadata

The canonical self-contained runtime probe snapshot is:

[`sanitized-runtime-probes-2026-07-17.json`](sanitized-runtime-probes-2026-07-17.json).

It transcribes only the metadata already retained in the five linked GitOps PR
comments. Each source comment is identified by immutable URL, comment ID,
author, timestamp and SHA-256 of the complete comment body. The artifact does
not retain questions, reviews, answers, PII, credentials, canary values or
Guardrail traces.

To verify provenance with an authenticated GitHub CLI session:

```powershell
gh api repos/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/issues/22/comments --paginate
```

Select the five comment IDs recorded in the JSON and SHA-256 the UTF-8 encoded
`body` field. The hashes must match `source_comments[*].body_sha256`.

This snapshot makes the accepted metadata available inside the source repo. It
does not recreate deleted probe Jobs or claim access to raw runtime content.
