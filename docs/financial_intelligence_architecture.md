# BankBuddy Financial Intelligence Architecture

**Date:** 2026-06-15
**Status:** Current v2 architecture direction
**Companion documents:**

- `docs/financial_intelligence_vision.md`
- `docs/financial_intelligence_open_questions.md`

## Executive Summary

BankBuddy should evolve into the broader personal financial intelligence
platform described in the product vision, while remaining in the existing
BankBuddy repository and keeping the `bankbuddy` CLI name.

The right target architecture is not a banking app with more tables. It is a
local-first evidence graph:

```text
Document -> Extraction -> Observation -> Entity/Relationship -> Inspection
```

The current BankBuddy implementation already has valuable mechanics that should
be retained: local SQLite, canonical storage, dry-run imports, parser staging,
file hashing, import attempt history, integer money storage, Base-style CLI
runtime, environment-specific data homes, and a growing parser test suite.

The current architecture should not constrain the next design. Because existing
data can be discarded, the cleanest path is a deliberate schema reset into a
versioned v2 model, not a long compatibility migration that preserves every old
bank/account assumption.

## Architecture Decisions

The following decisions define the current v2 direction:

- Keep the product and CLI name as `bankbuddy`.
- Use `Document`, `Entity`, `Observation`, and `Relationship` as the conceptual
  foundation, while allowing details to evolve during implementation.
- Use a v2 schema reset rather than compatibility migrations.
- Move imported documents into managed storage when an import activity finishes,
  whether the import succeeds or fails.
- Treat future `infer` work as read-only with respect to source documents unless
  a later design explicitly says otherwise.
- Pause TaxBuddy issue #100 until the v2 document/entity/observation model
  exists.
- Include household/person ownership in the v2 foundation schema.
- Allow raw extracted text storage before encryption if it materially helps the
  product, while still keeping encryption/keychain design as later hardening.
- Start net-worth reporting with native-currency buckets only; defer FX
  conversion.

The schema should also follow these conventions:

- All table names use the `BB_` prefix.
- Table names are singular.
- JSON values should be minimized. Prefer normalized relational tables because
  the data volume is small and reporting/queryability matters more than avoiding
  joins.
- Add indexes for common joins, lookups, date ranges, hashes, and status
  filters as part of each migration.
- Attribute values should be typed through `BB_ENTITY_ATTRIBUTE_TYPE` rather
  than stored as arbitrary key names.

## 1. Current-State Assessment

### What Exists Today

BankBuddy is currently a local-first Python CLI application with SQLite
persistence and two command surfaces:

- `bankbuddy`: banking statement import, account management, transactions,
  reports, audits, storage migration, repair, and export.
- `taxbuddy`: first tax-document readiness slice with document import,
  dry-run planning, canonical archival, and `docs list/show`.

Current core modules:

| Area | Current modules | Assessment |
|---|---|---|
| Runtime and paths | `runtime.py`, `paths.py`, `database.py` | Strong reusable foundation. |
| Banking model | `accounts.py`, `transactions.py`, `reports.py` | Useful but bank/account-centric. |
| Import pipeline | `imports.py`, `inbox.py`, `import_files.py`, `import_history.py`, `import_retry.py` | Strong mechanics, needs domain-generalization. |
| Parser logic | `imports.py`, `repairs.py`, tax parser in `tax/documents.py` | Works, but parser registration and routing are implicit in code. |
| Tax document index | `tax/documents.py`, `tax/cli.py`, migration `0009` | Useful first slice, should fold into generic document model. |
| Quality checks | `audit.py`, `statements.py`, duplicate diagnostics | Good inspect/report precedent. |
| Tests | broad pytest coverage | Retain patterns and fixtures, reorganize later. |

Current schema is centered on:

- `banks`
- `accounts`
- `transactions`
- `import_files`
- `import_attempts`
- `categories`
- `budgets`
- `tax_documents`

This is a coherent banking schema, not a complete financial intelligence
schema.

### Current Strengths To Preserve

- Local-first SQLite storage.
- Environment-specific app homes selected by `BANKBUDDY_ENV` and
  `BANKBUDDY_HOME`.
- Canonical data-home layout with `database/`, `bank/`, and `tax/`.
- Integer minor-unit storage for money.
- Parser staging before transaction commit.
- Dry-run parity for imports.
- File-level SHA-256 duplicate detection.
- Row-level transaction deduplication.
- Import attempt history with failure visibility.
- Content-based parser/account routing rather than filename inference.
- Pretty CLI table output and machine-friendly CSV/TSV paths where useful.
- Strong pytest coverage around import behavior.

### Current Things That Should Not Survive As Core Concepts

- `bank` as the top-level institution concept.
- `account` as the only financial object that can own transactions.
- Separate `tax_documents` as a long-term parallel document table.
- Banking and tax as separate storage worlds rather than views over documents,
  entities, observations, and relationships.
- Parser routing scattered through `imports.py` and `inbox.py`.
- Hard-coded currency checks limited to current supported currencies.

## 2. Gap Analysis

### Domain Gaps

| New requirement | Current limitation | Needed change |
|---|---|---|
| Documents as source of truth | Statement files and tax docs use separate tables | Create one `documents` table for all imported artifacts. |
| Assets and liabilities | Current schema only has bank accounts and transactions | Add explicit entities for accounts, properties, assets, liabilities, holdings, policies, and people. |
| Relationships | Current relationships are mostly foreign keys | Add first-class relationship records with provenance and validity ranges. |
| Infer workflow | Import commits final domain rows directly | Add observation candidates, confidence, review status, and acceptance workflow. |
| Inspect workflow | Current audits are banking-specific | Add deterministic inspection services over documents, entities, observations, and years. |
| Multi-year analysis | Statement audit exists, but not general timelines | Add validity periods, tax years, statement periods, valuation dates, and comparison reports. |
| Multi-currency net worth | Transactions store native currency but no FX model | Add exchange rates, base reporting currency, converted snapshots, and native amount preservation. |
| Multi-jurisdiction | Country codes exist but are shallow | Add jurisdictions as first-class metadata across documents, entities, accounts, assets, and observations. |
| Provenance | Transactions link to import files; tax docs link to source file | Generalize evidence links from observations to documents and extracted locations. |
| Review queue | No general accepted/rejected/needs-review model | Add review statuses to observations, relationships, and extracted entity candidates. |

### Architecture Gaps

- The CLI is a single large `cli.py`; this will become harder to maintain as
  `documents`, `infer`, `inspect`, `review`, `assets`, and `liabilities` grow.
- `imports.py` mixes parser detection, parsing, routing, account resolution,
  persistence, archive planning, and repair-sensitive legacy behavior.
- TaxBuddy is currently a separate package slice, but the new platform wants tax
  documents to be one document family inside the same evidence graph.
- The database migration chain assumes additive evolution. The new direction is
  a semantic schema reset.
- There is no repository/service layer boundary. Many modules open SQLite
  connections directly and issue SQL inline.

## 3. Proposed Target Architecture

### Core Model

Use four foundation concepts:

```text
Document
Entity
Observation
Relationship
```

Then add typed financial profiles for queryability:

```text
Person
Institution
Account
Asset
Liability
Property
Holding
Transaction
Balance
Valuation
Category
Budget
TaxSource
TaxGap
```

This hybrid model is important. Pure graph tables are flexible but painful for
financial reports. Pure typed tables are queryable but brittle as new document
families appear. The hybrid model gives both:

- generic evidence and inference through documents, entities, observations, and
  relationships;
- typed tables for high-value workflows such as transaction listing, net worth,
  tax readiness, and account continuity.

### Import, Infer, Inspect

The platform should formalize three stages:

1. **Import**
   - Accept a document.
   - Hash it.
   - Record a document/import attempt.
   - Classify type.
   - Extract text/metadata.
   - Archive or reference the file.

2. **Infer**
   - Run parser/interpreter rules.
   - Produce entity candidates, observation candidates, and relationship
     candidates.
   - Reconcile high-confidence candidates with existing entities.
   - Leave ambiguous candidates in a review queue.

3. **Inspect**
   - Produce deterministic reports from accepted data and review state.
   - Show gaps, continuity breaks, missing forms, missing periods, currency
     exposure, jurisdiction exposure, and net worth history.

This separation prevents parser code from directly polluting final tables.

Plain-language definitions:

- **Import** means "bring a document under BankBuddy management." Import hashes
  the file, records the attempt, extracts enough metadata to classify it, and
  moves the file into managed storage. Import should be conservative and should
  not invent financial conclusions.
- **Infer** means "propose facts from imported or externally supplied
  documents." For example, a 1099-INT may imply that an institution relationship
  existed for a tax year, and a statement may imply an account balance on a
  date. Infer should produce observations and review items. It should not move
  source documents, and it should not silently turn uncertain guesses into
  trusted records.
- **Inspect** means "query what BankBuddy already knows and show gaps,
  inconsistencies, or summaries." Inspect is deterministic reporting. It can
  answer questions such as "which documents are missing for 2025?", "which
  accounts existed last year but not this year?", and "what assets do I hold in
  each native currency?"
- **Provenance** means "show the evidence behind a fact." If BankBuddy says
  account 1234 existed in 2025, provenance is the path back to the document,
  parser, extraction run, and observation that support that statement.

It is possible that early v2 does not need a user-facing `infer` command. The
first implementation can start with import plus inspect, while keeping the
internal observation model ready for later inference and review workflows.

## 4. Proposed Domain Model

### Document

An immutable imported artifact or a referenced external artifact.

Examples: bank statement, credit-card statement, brokerage statement, 1099,
W-2, Form 26AS, AIS, mortgage statement, property tax bill, insurance policy.

Documents should track:

- original filename/path;
- canonical filename/path when copied into managed storage;
- SHA-256 hash;
- MIME/file type;
- document type;
- source institution when known;
- jurisdiction;
- period/tax year;
- processing status;
- parser/interpreter used;
- import attempt history.

### Entity

A durable real-world object in the user's financial graph.

Entity types should include:

- `person`
- `institution`
- `account`
- `asset`
- `liability`
- `property`
- `holding`
- `insurance_policy`
- `tax_source`
- `jurisdiction`

Important design point: not everything should be forced into `asset`. Credit
cards and mortgages are liabilities. Employers and tax agencies are
institutions or tax sources. Properties are assets but deserve typed fields.

### Observation

A fact extracted from a document or manually entered by the user.

Examples:

- account existed during a period;
- ending balance was X in currency Y on date Z;
- W-2 received from employer E for tax year 2025;
- 1099-INT reported interest income;
- property tax document received for property P;
- mortgage liability existed;
- brokerage account held a position.

Observations need:

- type;
- subject entity;
- optional related entity;
- document evidence;
- date or date range;
- amount/currency when applicable;
- confidence;
- extraction method;
- review status.

### Relationship

A typed connection between entities, optionally supported by a document.

Examples:

- person owns account;
- account held at institution;
- property secures mortgage liability;
- tax source expected to issue a document type;
- document issued by institution;
- account associated with tax source.

Relationships should include `valid_from` and `valid_to` where meaningful.

## 5. Proposed Entity Relationship Model

Conceptual ER:

```text
BB_DOCUMENT
  -> BB_IMPORT_ATTEMPT
  -> BB_EXTRACTION_RUN
  -> BB_OBSERVATION
  -> BB_OBSERVATION_EVIDENCE

BB_ENTITY
  -> BB_ENTITY_ATTRIBUTE
  -> BB_RELATIONSHIP

BB_ACCOUNT
  -> BB_ENTITY
  -> BB_INSTITUTION
  -> BB_TRANSACTION
  -> BB_BALANCE

BB_ASSET
  -> BB_ENTITY
  -> BB_VALUATION

BB_LIABILITY
  -> BB_ENTITY
  -> BB_BALANCE

BB_PROPERTY
  -> BB_ASSET

BB_TAX_SOURCE
  -> BB_ENTITY
  -> BB_EXPECTED_TAX_DOCUMENT
  -> BB_TAX_GAP

BB_DOCUMENT
  -> BB_TAX_GAP when received
```

The most important relationship is provenance:

```text
BB_OBSERVATION -> BB_OBSERVATION_EVIDENCE -> BB_DOCUMENT
```

Every meaningful inferred fact must be explainable through evidence.

## 6. Proposed Database Schema

This is a target schema proposal, not final DDL.

### Schema Naming and Normalization Rules

- Tables use `BB_` prefix and singular names.
- Table names are uppercase in the design for readability; SQLite itself is
  case-insensitive.
- Prefer normalized lookup/reference tables over JSON values.
- Use attribute type rows for flexible attributes. For example, a property
  address can be represented by typed rows such as `STREET_NUMBER`,
  `STREET_NUMBER_TYPE`, `ADDRESS_LINE_1`, `ADDRESS_CITY`,
  `ADDRESS_POSTAL_CODE`, `ADDRESS_STATE`, and `ADDRESS_COUNTRY`.
- Add indexes for each foreign key, unique business identity, document hash,
  date range, status, and report filter used by CLI commands.

### Core Tables

```sql
BB_SCHEMA_MIGRATION(
    version,
    applied_at
)

BB_DOCUMENT(
    document_id,
    file_hash,
    original_file_name,
    original_path,
    canonical_file_name,
    canonical_path,
    document_type,
    file_type,
    jurisdiction_code,
    period_start,
    period_end,
    tax_year,
    status,
    created_at,
    updated_at
)

BB_IMPORT_ATTEMPT(
    import_attempt_id,
    document_id,
    source_path,
    import_status,
    started_at,
    finished_at,
    parser_id,
    rows_parsed,
    rows_imported,
    rows_duplicate,
    error_message,
    created_at,
    updated_at
)

BB_PARSER(
    parser_id,
    parser_name,
    parser_family,
    document_type,
    file_type,
    institution_id,
    enabled,
    created_at,
    updated_at
)

BB_EXTRACTION_RUN(
    extraction_run_id,
    document_id,
    parser_id,
    extraction_method,
    confidence,
    status,
    created_at,
    updated_at
)
```

### Entity Graph Tables

```sql
BB_ENTITY(
    entity_id,
    entity_type,
    display_name,
    status,
    jurisdiction_code,
    created_at,
    updated_at
)

BB_ENTITY_ATTRIBUTE_TYPE(
    entity_attribute_type_id,
    attribute_code,
    display_name,
    value_kind,
    sensitivity,
    created_at,
    updated_at
)

BB_ENTITY_ATTRIBUTE(
    entity_attribute_id,
    entity_id,
    entity_attribute_type_id,
    attribute_value,
    source_document_id,
    created_at,
    updated_at
)

BB_RELATIONSHIP_TYPE(
    relationship_type_id,
    relationship_code,
    display_name,
    created_at,
    updated_at
)

BB_RELATIONSHIP(
    relationship_id,
    source_entity_id,
    relationship_type_id,
    target_entity_id,
    source_document_id,
    confidence,
    review_status,
    valid_from,
    valid_to,
    created_at,
    updated_at
)

BB_OBSERVATION_TYPE(
    observation_type_id,
    observation_code,
    display_name,
    created_at,
    updated_at
)

BB_OBSERVATION(
    observation_id,
    observation_type_id,
    subject_entity_id,
    related_entity_id,
    document_id,
    period_start,
    period_end,
    observation_date,
    amount_minor_units,
    currency_code,
    confidence,
    extraction_method,
    review_status,
    notes,
    created_at,
    updated_at
)

BB_OBSERVATION_EVIDENCE(
    evidence_id,
    observation_id,
    document_id,
    evidence_kind,
    evidence_ref,
    created_at,
    updated_at
)
```

### Typed Financial Tables

```sql
BB_PERSON(
    person_id,
    entity_id,
    display_name,
    person_role,
    created_at,
    updated_at
)

BB_INSTITUTION(
    institution_id,
    entity_id,
    name,
    institution_type,
    country_code,
    created_at,
    updated_at
)

BB_ACCOUNT(
    account_id,
    entity_id,
    institution_id,
    account_type,
    display_name,
    account_number,
    masked_account_ref,
    native_currency_code,
    jurisdiction_code,
    opened_date,
    closed_date,
    status,
    created_at,
    updated_at
)

BB_ASSET(
    asset_id,
    entity_id,
    asset_type,
    display_name,
    native_currency_code,
    jurisdiction_code,
    owner_person_id,
    related_account_id,
    status,
    created_at,
    updated_at
)

BB_LIABILITY(
    liability_id,
    entity_id,
    liability_type,
    institution_id,
    display_name,
    native_currency_code,
    jurisdiction_code,
    related_asset_id,
    status,
    created_at,
    updated_at
)

BB_PROPERTY(
    property_id,
    asset_id,
    display_name,
    property_type,
    country_code,
    region,
    city,
    ownership_type,
    created_at,
    updated_at
)
```

### Money, Transaction, and Valuation Tables

```sql
BB_TRANSACTION(
    transaction_id,
    account_id,
    document_id,
    category_id,
    transaction_date,
    amount_minor_units,
    currency_code,
    description,
    normalized_description,
    transaction_hash,
    transfer_pair_id,
    review_status,
    created_at,
    updated_at
)

BB_BALANCE(
    balance_id,
    account_id,
    document_id,
    balance_date,
    amount_minor_units,
    currency_code,
    balance_type,
    created_at,
    updated_at
)

BB_VALUATION(
    valuation_id,
    entity_id,
    document_id,
    valuation_date,
    amount_minor_units,
    currency_code,
    valuation_type,
    created_at,
    updated_at
)

BB_EXCHANGE_RATE(
    exchange_rate_id,
    base_currency_code,
    quote_currency_code,
    rate_date,
    rate,
    source,
    created_at,
    updated_at
)
```

### Tax Readiness Tables

```sql
BB_TAX_SOURCE(
    tax_source_id,
    entity_id,
    source_name,
    source_type,
    jurisdiction_code,
    active,
    created_at,
    updated_at
)

BB_EXPECTED_TAX_DOCUMENT(
    expected_tax_document_id,
    tax_source_id,
    expected_document_type,
    jurisdiction_code,
    expected_by_date,
    active,
    created_at,
    updated_at
)

BB_TAX_GAP(
    tax_gap_id,
    tax_year,
    expected_tax_document_id,
    received_document_id,
    status,
    notes,
    created_at,
    updated_at
)
```

### Reference Tables

```sql
BB_CURRENCY(currency_code, display_name, minor_unit_exponent)
BB_JURISDICTION(jurisdiction_code, display_name, country_code, region_code)
BB_CATEGORY(category_id, category_name, category_kind, is_system)
BB_CATEGORY_RULE(rule_id, pattern, category_id, priority, match_type, is_user_defined)
BB_BUDGET(budget_id, category_id, currency_code, budget_type, min_amount_minor_units, max_amount_minor_units)
```

### Initial Index Guidance

Create indexes alongside the v2 schema rather than as an afterthought:

```sql
BB_DOCUMENT(file_hash)
BB_DOCUMENT(document_type, tax_year)
BB_DOCUMENT(jurisdiction_code, tax_year)
BB_IMPORT_ATTEMPT(document_id, import_status)
BB_ENTITY(entity_type, status)
BB_ENTITY_ATTRIBUTE(entity_id, entity_attribute_type_id)
BB_RELATIONSHIP(source_entity_id, relationship_type_id)
BB_RELATIONSHIP(target_entity_id, relationship_type_id)
BB_OBSERVATION(subject_entity_id, observation_type_id)
BB_OBSERVATION(document_id)
BB_OBSERVATION(review_status)
BB_ACCOUNT(institution_id, account_type, status)
BB_TRANSACTION(account_id, transaction_date)
BB_TRANSACTION(category_id, transaction_date)
BB_TRANSACTION(currency_code, transaction_date)
BB_BALANCE(account_id, balance_date)
BB_VALUATION(entity_id, valuation_date)
BB_TAX_GAP(tax_year, status)
BB_TAX_SOURCE(jurisdiction_code, active)
```

## 7. Proposed Service Architecture

### Runtime and Configuration

Retain:

- current Base-style runtime options;
- environment-specific app homes;
- logging discipline;
- temporary directory cleanup;
- `uv` packaging and pytest validation.

Refactor:

- move runtime/config/path modules under `bankbuddy/core/` once the package
  structure changes.

### Document Service

Responsibilities:

- hash files;
- identify duplicates;
- create document records;
- plan/copy canonical storage;
- list/show documents;
- record import attempts.
- move completed import inputs into managed storage for both successful and
  failed import attempts.

Retain from current code:

- `hash_file`;
- canonical archive planning ideas;
- dry-run behavior;
- duplicate handling patterns.

Refactor from current code:

- merge `import_files` and `tax_documents` concepts into generic documents.

### Parser Registry and Extraction Service

Responsibilities:

- identify candidate parser by content signature;
- execute parser;
- return structured extraction results;
- never directly write final business tables.

Retain:

- BOA, Apple Card, ICICI, HDFC, and TaxBuddy parsing logic.

Refactor:

- move parser-specific logic out of the monolithic `imports.py`;
- define parser interfaces that return documents, observations, transactions,
  balances, relationships, and review candidates.

### Inference Service

Responsibilities:

- convert extraction results into observations and relationships;
- reconcile inferred entities against existing entities;
- auto-accept deterministic high-confidence facts;
- place ambiguous candidates into review.

Retain:

- account matching and statement reference concepts as a specific reconciliation
  rule.

Remove or demote:

- direct parser-to-account commit as the only successful import path.

The user-facing `infer` command remains a later design topic. The v2 foundation
should still model observations and relationships because they are useful even
when produced by deterministic parsers during import. A future infer workflow
should be read-only with respect to source documents: it may read documents or
existing extracted text, but it should not move or mutate input files.

### Inspection Service

Responsibilities:

- deterministic reports over accepted data and review state;
- document completeness;
- account continuity;
- tax gaps;
- currency exposure;
- jurisdiction exposure;
- review queues.

Retain:

- statement audit style;
- transaction list summary style;
- pretty table rendering conventions.

### Review Service

Responsibilities:

- accept/reject observations;
- merge inferred entities;
- waive expected documents;
- mark source inactive;
- preserve history.

This service is new and should be a first-class workflow, not an afterthought.

## 8. Proposed Package and Module Structure

Target structure:

```text
src/bankbuddy/
  __init__.py

  cli/
    __init__.py
    main.py
    documents.py
    import_cmd.py
    infer.py
    inspect.py
    review.py
    accounts.py
    assets.py
    liabilities.py
    tax.py
    reports.py

  core/
    config.py
    currency.py
    errors.py
    paths.py
    runtime.py
    tables.py

  db/
    connection.py
    migrations.py
    repositories/
      documents.py
      entities.py
      observations.py
      accounts.py
      transactions.py
      tax.py

  domain/
    documents.py
    entities.py
    observations.py
    relationships.py
    accounts.py
    assets.py
    liabilities.py
    properties.py
    tax.py
    money.py

  importers/
    base.py
    banking/
      boa.py
      apple_card.py
      hdfc.py
      icici.py
    tax/
      us_1099.py
      india.py
    documents.py

  inference/
    engine.py
    rules/
      banking.py
      tax.py
      real_estate.py
      investments.py

  inspection/
    engine.py
    reports/
      documents.py
      accounts.py
      tax_gaps.py
      currency.py
      jurisdiction.py

  review/
    workflow.py

tests/
  unit/
  integration/
  fixtures/
```

This can be reached gradually. Do not move everything in one PR.

## 9. Proposed CLI Evolution

The CLI should remain `bankbuddy` until the platform shape is stable. Separate
`taxbuddy` can remain temporarily, but the long-term command model should be
one platform CLI with domain groups.

Target command families:

```text
bankbuddy status
bankbuddy init

bankbuddy documents import FILE
bankbuddy documents inbox --dry-run
bankbuddy documents list
bankbuddy documents show DOCUMENT_ID

bankbuddy inspect documents --year YEAR
bankbuddy inspect gaps --year YEAR
bankbuddy inspect accounts --years 2024,2025
bankbuddy inspect review

bankbuddy review observations
bankbuddy review accept OBSERVATION_ID
bankbuddy review reject OBSERVATION_ID

bankbuddy entities list
bankbuddy entities show ENTITY_ID

bankbuddy accounts list
bankbuddy tx list
bankbuddy report spending
bankbuddy report net-worth

bankbuddy tax sources
bankbuddy tax gaps --year YEAR
bankbuddy tax summary --year YEAR
```

Potential later commands, only after the infer design is clarified:

```text
bankbuddy infer document DOCUMENT_ID
bankbuddy infer year YEAR
bankbuddy infer compare --years 2024,2025
```

Existing `bankbuddy import`, `bankbuddy tx`, `bankbuddy report`, and
`taxbuddy docs` can become compatibility commands during the transition, then
be retired once the new command surface is stable.

## 10. Future UI Architecture Recommendations

Do not start UI work until the domain model and CLI reports stabilize.

Recommended sequence:

1. CLI-first domain stabilization.
2. JSON output for inspect/review/report commands.
3. Local read-only web UI backed by the same Python services.
4. Optional Swift/macOS/iOS after storage, sync, and review semantics are
   stable.

The first UI should be read-only or review-oriented, not a full management UI.
The highest-value family UI is likely:

- net worth snapshot;
- documents received/missing;
- spending trends;
- tax readiness;
- review queue.

## 11. Refactoring and Migration Strategy

### Recommendation

Use a deliberate v2 schema reset.

Because backward compatibility is not required and existing data can be
discarded, avoid a fragile migration that tries to preserve old semantics.
However, do not silently destroy existing data homes. The migration path should
be explicit.

Possible command:

```text
bankbuddy storage reset-schema --to financial-intelligence-v2 --dry-run
bankbuddy storage reset-schema --to financial-intelligence-v2 --apply
```

The dry run should report:

- current schema version;
- tables that will be replaced;
- files left untouched;
- database backup/export recommendation;
- new schema version.

Because compatibility is explicitly not required, this reset can discard
transaction/account rows. The command must still avoid accidental data loss by
requiring an explicit `--apply` mode and clear user-facing output.

### Retain

- Python package and repo.
- `pyproject.toml` / `uv` workflow.
- Base-style runtime.
- `paths.py` environment semantics.
- SQLite migration mechanism, possibly moved under `db/`.
- Current parser test fixtures and parser-specific knowledge.
- Currency minor-unit discipline.
- CLI rendering style.

### Remove As Canonical

- `banks` as the root institution table.
- `tax_documents` as a separate standalone document index.
- `import_files` as banking-only document metadata.
- `import_attempts` as banking-only attempts.
- hard-coded banking inbox as the only import path.

### Refactor

- `imports.py` into parser modules plus document/import services.
- `inbox.py` into a generic document inbox processor with domain-specific
  parser dispatch.
- `accounts.py` into accounts plus institutions plus entity reconciliation.
- `transactions.py` to reference `documents` and typed accounts.
- `tax/documents.py` into generic documents plus tax extraction rules.
- `cli.py` into command-group modules.

## 12. Phased Implementation Plan

### Phase 0: Architecture Ratification

Deliverables:

- Confirm the accepted review decisions in a committed design PR.
- Create issue-backed implementation slices for the v2 foundation.
- Close, pause, or reframe issue #100 until the v2 document model exists.

No code changes.

### Phase 1: V2 Foundation Schema

Build:

- `documents`
- `import_attempts`
- `parsers`
- `entities`
- `entity_attribute_types`
- `entity_attributes`
- `relationship_types`
- `relationships`
- `observation_types`
- `observations`
- `observation_evidence`
- reference tables for currencies and jurisdictions

Validation:

- migration tests;
- repository tests;
- document import dry-run and real import tests using synthetic fixtures.
- index presence tests for key report and join paths.

### Phase 2: Generic Document Import

Build:

- `bankbuddy documents import`;
- `bankbuddy documents inbox --dry-run`;
- document listing/show commands;
- generic duplicate detection;
- managed document archive paths;
- managed failed-import archive paths.

Retain parser behavior but write to `documents` first.

### Phase 3: Parser Interface and Existing Banking Parser Migration

Build:

- parser registry in code with database metadata;
- parser interface returning extraction results;
- BOA, Apple Card, ICICI, HDFC migrated behind the interface.

Goal:

- existing banking imports work through document/import/extraction pipeline.

### Phase 4: Transaction and Balance Projection

Build:

- transactions as accepted projections from observations/extractions;
- balances table;
- account continuity inspection;
- existing `tx list` and spending reports on v2 schema.

### Phase 5: Tax Readiness On V2

Build:

- tax source model;
- expected tax documents;
- tax gaps;
- annual tax readiness summary;
- replace or fold in current `taxbuddy` commands.

This is the v2 version of issue #100.

### Phase 6: Observation Review Workflow

Build:

- observation review queue;
- accept/reject/supersede commands;
- entity merge/link commands;
- confidence and provenance display.

### Phase 7: Optional Infer Workflow

Build:

- read-only inference over imported documents and accepted observations;
- commands only if inspect/report workflows are insufficient;
- no source document movement or mutation.

### Phase 8: Assets, Liabilities, Properties, Net Worth

Build:

- typed asset/liability/property tables;
- valuation snapshots;
- net worth reports per native currency;
- no FX conversion in the first net-worth report.

### Phase 9: Multi-Currency Conversion

Build:

- exchange rates;
- FX source tracking;
- base reporting currency;
- converted amount views.

Do not overwrite native amounts.

### Phase 10: UI Readiness

Build:

- JSON output for document, inspect, review, and report commands;
- stable service methods for UI consumption;
- local read-only web UI spike.

## 13. Recommendation By Current Code Area

| Current area | Keep | Remove | Refactor |
|---|---|---|---|
| Runtime | Base-style CLI setup, logging, env selection | Nothing material | Move to `core/` later. |
| Paths | Environment homes, canonical layout | Bank/tax-only assumption as final shape | Add generic `documents/` roots. |
| Database | Migration runner, SQLite connection discipline | Old schema as canonical | Introduce explicit v2 reset/migrations. |
| Imports | Parsers, dry-run, hash, staging, duplicate logic | Parser-to-account direct coupling | Split into document service, parser service, inference service. |
| Accounts | Account setup, account refs, masking | Bank as root concept | Generalize bank to institution and account to typed entity. |
| Transactions | Minor units, categories, filters, reports | Account-only worldview | Reference documents and v2 accounts. |
| TaxBuddy | Metadata extraction and CLI learnings | Separate tax document index as long-term model | Fold into generic documents and tax observations. |
| CLI | Click conventions, pretty tables, debug options | Single monolithic `cli.py` | Split command groups. |
| Tests | Broad pytest discipline | Old schema assertions after v2 lands | Reorganize fixtures and integration flows. |

## 14. Design Risks

### Risk: Over-Generic Graph Model

If everything becomes `entities` and JSON attributes, reports become painful.
Mitigation: use hybrid model with typed tables for accounts, transactions,
assets, liabilities, properties, tax sources, balances, and valuations. Use
`BB_ENTITY_ATTRIBUTE_TYPE` for flexible attributes rather than arbitrary JSON.

### Risk: Big-Bang Refactor

A full rewrite would stall useful progress.
Mitigation: make v2 foundation explicit, then migrate one workflow at a time:
documents, banking import, transactions, tax readiness, net worth.

### Risk: AI Contaminates Trusted State

AI extraction can be wrong.
Mitigation: all AI-derived facts become observations with confidence and review
status. Only accepted/high-confidence deterministic observations project into
reports.

### Risk: Net Worth Without FX Semantics

Consolidated wealth across USD/INR without rate provenance is misleading.
Mitigation: report native currency first; add base-currency reporting only with
exchange-rate source/date tracking.

### Risk: Sensitive Data Leakage

Document text, account numbers, PAN/SSN-like identifiers, and addresses are
sensitive.
Mitigation: classify attribute sensitivity, avoid raw text in normal logs, mask
CLI output, and defer durable text indexing until encryption is designed.

## 15. Resolved Decisions

Resolved decisions:

1. Keep the user-facing product and CLI name as `BankBuddy` / `bankbuddy`.
2. Use `Document/Entity/Observation/Relationship` as the foundation, with
   details refined during implementation.
3. Use a schema reset path instead of compatibility migrations.
4. Move documents into managed storage after completed import attempts,
   including failures.
5. Pause issue #100 until the v2 document/entity model exists.
6. Include household/person ownership in the v2 foundation schema.
7. Allow raw extracted text storage before encryption if needed, but keep
   encryption/keychain design as later hardening.
8. Start net-worth reporting with native-currency buckets only.

Open design topics are tracked in
`docs/financial_intelligence_open_questions.md`.

## 16. Bottom Line

The new design direction should not be implemented as "BankBuddy plus more
tables." The right move is to preserve the proven local runtime and import
mechanics while replacing the domain center with documents, entities,
observations, and relationships.

The next architecture implementation slice is the v2 foundation schema. TaxBuddy
issue #100 stays paused until the generic document/entity/observation model
exists, then it can be reframed as a Tax Readiness projection over that model.
