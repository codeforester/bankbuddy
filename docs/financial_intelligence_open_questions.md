# BankBuddy Financial Intelligence Open Questions

**Status:** Living design queue
**Companion documents:**

- `docs/financial_intelligence_vision.md`
- `docs/financial_intelligence_architecture.md`

This document tracks unresolved design topics for the financial intelligence v2
architecture. Resolved decisions belong in the architecture document. Stale
questions should be removed when the implementation or a later design decision
settles them.

## User-Facing Infer

Early v2 might not need a user-facing `bankbuddy infer` command. Deterministic
parsers can create observations during import, and inspect/report commands can
surface gaps and review items.

Open question:

- Should `infer` become a separate user command, or should inference remain an
  internal service until import plus inspect proves insufficient?

Current bias:

- Build the v2 schema and observation model first.
- Keep source documents read-only for any future infer operation.
- Add user-facing infer only when there is a clear workflow that import,
  inspect, and review do not cover.

## Raw Extracted Text Storage

Raw extracted text can make debugging, provenance, search, and future inference
much better. It also increases privacy risk because statements, tax forms,
account numbers, addresses, and identifiers may be stored outside the original
document.

Open questions:

- Should raw extracted text be stored by default?
- Should it be stored only for selected document types?
- Should it be an optional debug/audit feature?
- Should durable raw text storage wait for encryption/keychain support?

Current bias:

- Allow the architecture to support extracted text.
- Avoid requiring raw text persistence in the first v2 schema slice unless it is
  needed for tests, provenance, or inspect commands.
- Keep debug logs and normal CLI output free of raw document content.

## Managed Document View Reconciliation

BankBuddy v2 separates authoritative canonical document objects from generated
human-readable views. This keeps the database and canonical store authoritative
while preserving the transparent browsable filesystem experience that made v1
easy to understand.

Open questions:

- How should BankBuddy detect that a user edited, moved, or deleted generated
  view copies?
- Should view reconciliation run automatically during status/import, or only
  through an explicit inspect/repair command?
- What should the repair UX look like when a view is missing but the canonical
  object is intact?
- Should exact duplicates continue to be preserved under the v2 duplicates root,
  or eventually be deleted after recording the duplicate attempt?

Current bias:

- Keep `financial/canonical` as the source of truth.
- Treat `financial/views` as generated copies that can be rebuilt.
- Preserve source documents after every completed import attempt by recording a
  canonical object or managed failed/duplicate object.
- Keep duplicate preservation for now because it is useful while the product is
  still young.
- Use explicit inspect/repair commands before adding automatic repair behavior.

## Type Dictionary Seed Values

The v2 schema should use typed dictionaries instead of arbitrary JSON keys.
The first schema slice needs enough seed data to support accounts, people,
institutions, documents, observations, and relationships without pretending to
cover every future domain.

Open questions:

- What initial values belong in `BB_ENTITY_ATTRIBUTE_TYPE`?
- What initial values belong in `BB_RELATIONSHIP_TYPE`?
- What initial values belong in `BB_OBSERVATION_TYPE`?
- Which type values are system-managed versus user-created?

Current bias:

- Seed only the values needed by the first v2 implementation slice.
- Keep type dictionaries extensible.
- Treat addresses, account identifiers, jurisdictions, ownership, statement
  periods, balances, and document identifiers as first-class typed values rather
  than JSON blobs.

## AI And Local Model Strategy

The platform may eventually use AI to classify documents, extract fields,
summarize evidence, and suggest relationships. AI output must not become trusted
state without provenance and review semantics.

Open questions:

- Should the first AI-assisted workflows require local-only models?
- Should optional remote LLM calls be allowed with explicit user approval?
- How should prompts, extracted text, and outputs be logged or redacted?
- What confidence and review thresholds are required before AI output affects
  reports?

Current bias:

- Start with deterministic parsers and rule-based inference.
- Design interfaces that can accept AI-generated observations later.
- Treat AI output as proposed observations, not facts.

## Tax Readiness On V2

TaxBuddy issue #100 is paused until the v2 document/entity/observation
foundation exists. The tax readiness feature should become a projection over
documents, tax sources, expected document types, observations, and review state.

Open questions:

- Which tax-source and expected-document concepts belong in the first v2 tax
  slice?
- How should manual overrides be modeled without weakening provenance?
- How much jurisdiction-specific tax semantics should BankBuddy store before it
  risks looking like tax advice?

Current bias:

- Keep tax readiness focused on document completeness and evidence.
- Avoid tax filing, tax strategy, and legal advice.
- Build annual readiness summaries only after generic documents and
  observations are in place.
