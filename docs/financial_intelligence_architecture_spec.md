# BankBuddy Financial Intelligence Platform
## Comprehensive Architecture Specification

**Status:** Draft architecture specification
**Audience:** Codex, future maintainers, product/design review
**Source:** Design discussion expanding BankBuddy from a banking tool into a local-first personal financial intelligence platform.

---

# 1. Executive Summary

BankBuddy began as a personal banking application focused on accounts, balances, and transactions.

The product direction has now expanded.

The new vision is to evolve BankBuddy into a **Personal Financial Intelligence Platform**: a local-first, privacy-preserving system that helps individuals understand their complete financial life across documents, accounts, assets, liabilities, jurisdictions, currencies, and time.

This is not a tax filing product.

This is not a CPA replacement.

This is not a professional financial advisory tool.

The goal is to help ordinary individuals gain clarity over their financial world by organizing source documents, extracting facts, inferring relationships, detecting gaps, and producing understandable views of their financial position.

The most important new capability is the distinction between:

- **Import** — bring documents and structured files into the system.
- **Infer** — derive financial facts and relationships from documents.
- **Inspect** — determine completeness, gaps, inconsistencies, and year-over-year changes.

---

# 2. Product Vision

## 2.1 Mission

BankBuddy should help a user answer:

- What financial accounts do I have?
- What assets do I own?
- What liabilities do I owe?
- What documents prove or explain these things?
- What changed between last year and this year?
- What documents are missing?
- What accounts or assets appear in one year but not another?
- What institutions am I financially connected to?
- What is my total picture across countries and currencies?

The intended feeling for the user is:

> “I finally understand my financial picture.”

---

## 2.2 Non-Goals

BankBuddy should not initially attempt to:

- File tax returns.
- Replace a CPA.
- Provide legal advice.
- Provide tax advice.
- Recommend investments.
- Optimize tax strategy.
- Connect to live bank feeds before the local model is solid.
- Become enterprise accounting software.

The platform is for personal understanding, organization, and insight.

---

# 3. Design Principles

## 3.1 Local First

The primary architecture must be local-first.

All core functionality should run on the user's machine:

- Data ingestion
- Document storage references
- Metadata extraction
- SQLite database
- Inference engine
- Inspection reports
- CLI workflows
- Future local UI

No cloud service should be required for the product to function.

---

## 3.2 Privacy First

Financial documents are deeply sensitive.

The default posture:

- Do not upload user documents.
- Do not require remote processing.
- Do not store personal financial data outside the local machine.
- Treat document contents, extracted facts, and inferred observations as private user data.

Any future cloud sync must be explicit, optional, and user-controlled.

---

## 3.3 Cloud Optional

Future synchronization can be considered through user-controlled platforms such as:

- Apple CloudKit
- iCloud private containers
- Local network sync
- User-owned encrypted storage

Cloud sync must not become a requirement.

---

## 3.4 AI-Assisted, Not AI-Dependent

AI may assist with:

- Document classification
- Field extraction
- Account/entity recognition
- Relationship inference
- Summarization
- Missing-document detection
- Natural-language explanations

But the system should retain explicit structured data models and deterministic inspection logic.

AI output should be treated as proposed observations, not unquestioned truth.

---

## 3.5 Traceability

Every inferred fact should be traceable back to source material.

A user should be able to ask:

- Where did this account come from?
- Which document showed this amount?
- Why did the system infer this institution?
- What evidence supports this observation?

This implies a strong provenance model.

---

## 3.6 Refactoring Is Allowed

Existing BankBuddy code should not constrain the correct long-term design.

Allowed:

- Schema redesign
- Entity redesign
- Package restructuring
- CLI redesign
- Service boundary redesign
- Test reorganization

Backward compatibility is not a primary concern at this stage.

Existing data can be discarded if necessary.

---

# 4. Conceptual Product Expansion

## 4.1 Original BankBuddy Scope

The original application was banking-oriented.

Likely concepts:

- Bank accounts
- Transactions
- Balances
- Institutions
- Imports
- Reports

This remains valuable but becomes one part of a larger model.

---

## 4.2 Expanded Scope

BankBuddy should support the following domains.

### Banking

- Checking accounts
- Savings accounts
- Certificates of deposit
- Money market accounts
- Interest income

### Investments

- Brokerage accounts
- Stocks
- ETFs
- Mutual funds
- Bonds
- Dividends
- Capital gains documents

### Retirement

- 401(k)
- IRA
- Roth IRA
- Pension accounts
- Retirement statements

### Real Estate

- Primary residence
- Rental properties
- Property tax documents
- Mortgage documents
- Rental income records

### Liabilities

- Mortgages
- HELOCs
- Credit cards
- Personal loans
- Auto loans

### Insurance

- Health insurance
- Life insurance
- Auto insurance
- Property insurance
- COBRA / ACA documents

### Tax Documents

- W-2
- 1099-INT
- 1099-DIV
- 1099-B
- 1099-R
- K-1
- Property tax forms
- Foreign income documents
- India tax documents
- Brokerage tax packages

### International Assets

- US accounts
- India accounts
- Foreign real estate
- Foreign rental income
- Multi-currency balances

---

# 5. Core Architectural Vocabulary

The foundational architecture should be built around three primary abstractions:

```text
Document
Entity
Observation
```

These three concepts allow the system to remain general, extensible, and traceable.

---

## 5.1 Document

A **Document** is an imported artifact.

Examples:

- PDF tax return
- Bank statement
- Brokerage statement
- Spreadsheet
- CSV export
- Property tax bill
- Rental income statement
- Insurance policy
- Loan statement

Documents are source material.

Documents should be treated as immutable once imported.

Possible document properties:

- Document ID
- File path
- Original filename
- File hash
- MIME type
- Document type
- Source institution
- Jurisdiction
- Tax year
- Statement period start
- Statement period end
- Import timestamp
- Processing status

---

## 5.2 Entity

An **Entity** is a real-world financial object discovered or manually entered.

Examples:

- Person
- Institution
- Account
- Property
- Loan
- Insurance policy
- Investment holding
- Tax form issuer
- Currency
- Jurisdiction

Entities are the durable objects in the user's financial graph.

Possible entity types:

- `person`
- `institution`
- `account`
- `asset`
- `liability`
- `property`
- `investment_holding`
- `insurance_policy`
- `tax_form`
- `currency`
- `jurisdiction`

---

## 5.3 Observation

An **Observation** is a fact asserted or inferred from a document.

Examples:

- “This document contains a 1099-INT from Capital One.”
- “Interest income of $3,200 was reported for 2025.”
- “Account ending in 1234 existed in 2025.”
- “A rental property generated income in 2025.”
- “A mortgage liability existed during the statement period.”
- “This Indian bank account had INR-denominated funds.”

Observations should have provenance.

Possible observation properties:

- Observation ID
- Observation type
- Subject entity ID
- Related entity ID
- Source document ID
- Tax year
- Amount
- Currency
- Date or date range
- Confidence score
- Extraction method
- Human review status
- Raw extracted text reference
- Notes

Observation confidence is important because AI-generated extraction may be uncertain.

---

# 6. Import → Infer → Inspect Architecture

The system should explicitly separate these workflows.

---

## 6.1 Import

Import answers:

> “What files or structured records have entered the system?”

Responsibilities:

- Accept files from CLI.
- Compute file hash.
- Store document metadata.
- Classify document type if possible.
- Avoid duplicate imports.
- Record source path.
- Optionally copy files into a managed local document store.
- Extract basic text and metadata.

Example CLI:

```bash
bankbuddy import ~/Documents/Taxes/2025/1099-capitalone.pdf
bankbuddy import ~/Downloads/fidelity-2025-tax-package.pdf --tax-year 2025
bankbuddy import ~/Documents/India/icici-statement.xlsx --jurisdiction IN --currency INR
```

---

## 6.2 Infer

Infer answers:

> “What can we conclude from the available documents?”

Responsibilities:

- Parse document contents.
- Extract candidate entities.
- Extract candidate observations.
- Match observations to existing entities.
- Detect new entities.
- Detect relationships.
- Compare across years.
- Produce inference reports.

Examples:

- A 1099-INT implies a bank relationship.
- A 1099-DIV implies brokerage or investment holdings.
- Rental income implies rental property.
- Mortgage interest implies mortgage liability.
- Foreign bank statement implies foreign financial account.
- A prior-year account missing in current year implies a possible missing document or closed account.

Example CLI:

```bash
bankbuddy infer --tax-year 2025
bankbuddy infer --document DOC123
bankbuddy infer --compare-years 2024 2025
```

---

## 6.3 Inspect

Inspect answers:

> “What do we have, what is missing, and what needs attention?”

Responsibilities:

- Show imported documents by year.
- Show documents by institution.
- Show accounts with missing statements.
- Show tax years with incomplete coverage.
- Show inferred entities needing review.
- Show confidence warnings.
- Show year-over-year changes.

Examples:

```bash
bankbuddy inspect --tax-year 2025
bankbuddy inspect documents --tax-year 2025
bankbuddy inspect gaps --compare-years 2024 2025
bankbuddy inspect entities --unreviewed
```

---

# 7. Domain Model

## 7.1 Person

Represents a human connected to the financial graph.

Examples:

- User
- Spouse
- Dependent
- Joint account holder

Suggested fields:

- `id`
- `display_name`
- `role`
- `notes`
- `created_at`
- `updated_at`

---

## 7.2 Institution

Represents an organization.

Examples:

- Bank of America
- Fidelity
- ICICI Bank
- UnitedHealthcare
- County tax office

Suggested fields:

- `id`
- `name`
- `institution_type`
- `country_code`
- `website`
- `notes`

---

## 7.3 Account

Represents a financial account.

Examples:

- Checking account
- Savings account
- Brokerage account
- 401(k)
- IRA
- NRE account
- NRO account

Suggested fields:

- `id`
- `institution_id`
- `account_type`
- `display_name`
- `masked_account_number`
- `currency_code`
- `jurisdiction_code`
- `opened_date`
- `closed_date`
- `status`
- `notes`

---

## 7.4 Asset

Represents something owned.

Examples:

- Bank balance
- Brokerage portfolio
- Real estate
- Stock position
- Retirement balance

Suggested fields:

- `id`
- `asset_type`
- `display_name`
- `currency_code`
- `jurisdiction_code`
- `owner_person_id`
- `related_account_id`
- `notes`

---

## 7.5 Liability

Represents something owed.

Examples:

- Mortgage
- HELOC
- Credit card balance
- Auto loan

Suggested fields:

- `id`
- `liability_type`
- `display_name`
- `institution_id`
- `currency_code`
- `jurisdiction_code`
- `related_asset_id`
- `opened_date`
- `closed_date`
- `status`
- `notes`

---

## 7.6 Property

Real estate deserves explicit modeling.

Suggested fields:

- `id`
- `display_name`
- `property_type`
- `country_code`
- `region`
- `city`
- `currency_code`
- `ownership_type`
- `notes`

Avoid storing precise street addresses unless the user explicitly wants them.

---

## 7.7 Document

Covered earlier.

---

## 7.8 Observation

Covered earlier.

---

## 7.9 Relationship

Relationships connect entities.

Examples:

- Person owns account.
- Account belongs to institution.
- Property has mortgage liability.
- Document supports account.
- Observation references asset.
- Institution issued document.

Suggested fields:

- `id`
- `source_entity_id`
- `relationship_type`
- `target_entity_id`
- `source_document_id`
- `confidence`
- `valid_from`
- `valid_to`
- `notes`

---

# 8. Proposed ER Model

Initial conceptual ER structure:

```text
Person
  └── owns/manages ── Account
                         └── held_at ── Institution

Person
  └── owns ── Asset
                 └── may_be_backed_by ── Account

Person
  └── owes ── Liability
                  └── owed_to ── Institution

Property
  └── secured_by ── Liability

Document
  └── produces ── Observation
                       └── references ── Entity

Observation
  └── supported_by ── Document

Entity
  └── related_to ── Entity
```

The key is not to overfit early.

The `Entity` and `Relationship` abstraction allows broad modeling without requiring a separate table for every possible real-world object immediately.

---

# 9. Suggested SQLite Schema Direction

This is a starting point, not final DDL.

## 9.1 Core Tables

```sql
documents
document_texts
entities
entity_attributes
relationships
observations
observation_evidence
imports
processing_runs
```

---

## 9.2 Reference Tables

```sql
currencies
jurisdictions
institution_aliases
document_type_patterns
entity_type_definitions
observation_type_definitions
```

---

## 9.3 Financial Tables

Depending on the current BankBuddy structure, retain or redesign:

```sql
accounts
transactions
balances
assets
liabilities
properties
holdings
```

These can either be first-class tables or specialized entity profiles.

---

## 9.4 Recommended Hybrid Model

Use both:

1. Generic graph-like tables:
   - `entities`
   - `relationships`
   - `observations`

2. Domain-specific tables:
   - `accounts`
   - `transactions`
   - `balances`
   - `assets`
   - `liabilities`
   - `properties`

This gives flexibility and queryability.

---

# 10. Observation Model

Observation types should be explicit.

Examples:

```text
account_existence
account_balance
interest_income
dividend_income
capital_gain
rental_income
mortgage_interest
insurance_coverage
tax_form_received
foreign_account_presence
property_ownership
liability_existence
```

Each observation should include:

- Type
- Source document
- Subject entity
- Amount if applicable
- Currency if applicable
- Period
- Confidence
- Extraction method
- Review status

Review statuses:

```text
new
accepted
rejected
needs_review
superseded
```

---

# 11. Inference Engine Design

## 11.1 Pipeline

```text
Document
  -> classify
  -> extract text
  -> extract fields
  -> detect entities
  -> generate observations
  -> reconcile with existing graph
  -> produce inference report
```

---

## 11.2 Rule-Based Inference

Start with deterministic rules.

Examples:

```text
If document type is 1099-INT:
  create/confirm institution
  create interest_income observation
  create account_existence observation if account identifier is present

If document type is mortgage statement:
  create/confirm liability
  create mortgage_interest observation
  link liability to property if known

If document contains rental income:
  create/confirm property asset
  create rental_income observation
```

---

## 11.3 AI-Assisted Inference

AI can be added behind explicit interfaces.

Example interface:

```python
class DocumentInterpreter:
    def classify(document) -> DocumentClassification
    def extract_entities(document) -> list[EntityCandidate]
    def extract_observations(document) -> list[ObservationCandidate]
```

Possible implementations:

- Regex/rule-based interpreter
- Local ML model interpreter
- Optional LLM interpreter
- Manual interpreter

The rest of the architecture should not care which interpreter generated the candidates.

---

## 11.4 Confidence and Human Review

Every inferred item should have:

- Confidence score
- Evidence reference
- Review status

High-confidence deterministic facts can be auto-accepted.

Low-confidence AI facts should require review.

---

# 12. Inspect Engine Design

Inspect should be deterministic and report-oriented.

Examples of inspection reports:

## 12.1 Document Completeness Report

Questions:

- Which documents exist for tax year 2025?
- Which institutions have documents?
- Which expected documents are missing?

## 12.2 Account Continuity Report

Questions:

- Which accounts existed in 2024?
- Which accounts exist in 2025?
- Which disappeared?
- Which are new?

## 12.3 Jurisdiction Report

Questions:

- Which assets are US-based?
- Which assets are India-based?
- Which documents support each jurisdiction?

## 12.4 Currency Exposure Report

Questions:

- What assets are denominated in USD?
- What assets are denominated in INR?
- What is the converted base-currency value?

## 12.5 Review Queue

Questions:

- Which observations need human review?
- Which entities were inferred but not accepted?
- Which documents failed parsing?

---

# 13. Multi-Year Timeline Architecture

Time is central to the platform.

The system should model:

- Calendar year
- Tax year
- Statement period
- Observation date
- Account open/close range
- Asset valuation date
- Liability balance date

Useful commands:

```bash
bankbuddy timeline --entity ACCOUNT123
bankbuddy compare --years 2024 2025
bankbuddy inspect gaps --years 2024 2025
```

---

# 14. Multi-Currency Architecture

Currencies should be first-class.

Required fields:

- Native currency
- Base reporting currency
- FX rate date
- FX source
- Converted amount

Suggested tables:

```sql
currencies
exchange_rates
amounts
```

Do not overwrite native values.

Always preserve:

- Original amount
- Original currency
- Converted amount
- Conversion rate
- Conversion date

---

# 15. Multi-Jurisdiction Architecture

Jurisdiction should be metadata, not hard-coded tax logic.

Track:

- Country code
- State/region if needed
- Institution jurisdiction
- Asset jurisdiction
- Account jurisdiction
- Document jurisdiction
- Tax year

Start simple:

```text
US
IN
```

Avoid building a tax engine initially.

Instead, produce organization and completeness insights.

---

# 16. CLI Architecture

The CLI should remain the first product interface.

Suggested command groups:

```bash
bankbuddy init
bankbuddy import
bankbuddy documents
bankbuddy infer
bankbuddy inspect
bankbuddy entities
bankbuddy accounts
bankbuddy assets
bankbuddy liabilities
bankbuddy properties
bankbuddy observations
bankbuddy review
bankbuddy report
bankbuddy db
```

---

## 16.1 Example CLI Workflows

### Import a document

```bash
bankbuddy import ~/Documents/Taxes/2025/fidelity-tax-package.pdf --tax-year 2025
```

### Infer from imported documents

```bash
bankbuddy infer --tax-year 2025
```

### Inspect current tax year completeness

```bash
bankbuddy inspect --tax-year 2025
```

### Compare two years

```bash
bankbuddy inspect gaps --years 2024 2025
```

### Review AI-generated observations

```bash
bankbuddy review observations --status needs_review
```

### Accept an observation

```bash
bankbuddy review accept OBS123
```

---

# 17. Package / Module Structure

Suggested Python package structure:

```text
bankbuddy/
  __init__.py
  cli/
    __init__.py
    main.py
    import_cmd.py
    infer_cmd.py
    inspect_cmd.py
    review_cmd.py
    report_cmd.py

  core/
    __init__.py
    config.py
    paths.py
    errors.py
    types.py

  db/
    __init__.py
    connection.py
    migrations.py
    schema.sql
    repositories/

  domain/
    __init__.py
    documents.py
    entities.py
    observations.py
    relationships.py
    accounts.py
    assets.py
    liabilities.py
    properties.py
    currencies.py
    jurisdictions.py

  importers/
    __init__.py
    base.py
    pdf_importer.py
    csv_importer.py
    spreadsheet_importer.py

  interpreters/
    __init__.py
    base.py
    rule_based.py
    llm_optional.py

  inference/
    __init__.py
    engine.py
    rules/
      tax_forms.py
      banking.py
      investments.py
      real_estate.py
      insurance.py

  inspection/
    __init__.py
    engine.py
    reports/
      documents.py
      gaps.py
      continuity.py
      currency.py
      jurisdiction.py

  review/
    __init__.py
    workflow.py

  reporting/
    __init__.py
    markdown.py
    json.py
    tables.py

tests/
  unit/
  integration/
  fixtures/
```

---

# 18. Testing Strategy

Testing should include:

## 18.1 Unit Tests

- Document classification
- Entity creation
- Observation creation
- Rule inference
- Currency conversion
- Relationship creation

## 18.2 Integration Tests

- Import sample document
- Run inference
- Inspect output
- Verify database state

## 18.3 Fixture Documents

Use synthetic fixture documents.

Do not commit real financial documents.

Create artificial examples:

- Fake 1099-INT
- Fake bank statement
- Fake mortgage statement
- Fake rental summary
- Fake India bank statement

---

# 19. Security and Privacy

## 19.1 Data Storage

Use local SQLite.

Default database location might be:

```text
~/.bankbuddy/bankbuddy.db
```

Documents can remain in place or be copied into:

```text
~/.bankbuddy/documents/
```

If copied, preserve original filename and hash.

---

## 19.2 Sensitive Data Handling

Avoid logging:

- Account numbers
- Full document text
- SSNs
- Tax IDs
- Precise addresses
- Full financial details

Use masked identifiers in CLI output.

---

## 19.3 Optional Encryption

Future:

- SQLCipher
- macOS Keychain integration
- Encrypted document store

Not required for first architecture pass, but leave room for it.

---

# 20. Future UI Architecture

## 20.1 Local Web UI

Possible stack:

- Python backend
- FastAPI
- SQLite
- React or simple server-rendered UI

Advantages:

- Cross-platform
- Easier rapid iteration
- Works with existing Python backend

---

## 20.2 Native macOS App

Possible stack:

- Swift
- SwiftUI
- SQLite access
- Local service bridge to Python engine if needed

Advantages:

- Native Apple experience
- Better document handling
- Better iCloud / CloudKit future path
- Better iPhone/iPad extension later

---

## 20.3 iOS / iPadOS App

Possible only after the domain and local data model are stable.

Potential uses:

- Read-only dashboard
- Document capture
- Review queue
- Notifications
- iCloud sync

---

## 20.4 CloudKit Future

CloudKit can be considered for private user sync.

Design requirement:

- Sync should be optional.
- User data should remain private.
- Local-first architecture must remain valid without sync.

---

# 21. Migration / Refactoring Strategy

Since existing data can be discarded, prefer clean architecture.

Suggested approach:

## Phase 0: Architecture Review

Codex should inspect current code and produce:

- Existing module map
- Existing schema
- Current CLI commands
- Current domain model
- Current test coverage
- Reusable components
- Components to discard

No implementation in this phase.

---

## Phase 1: New Core Domain

Introduce:

- Document
- Entity
- Observation
- Relationship

Add migrations and repositories.

---

## Phase 2: Import System

Implement:

- File import
- Hashing
- Metadata capture
- Duplicate detection
- Document listing

---

## Phase 3: Rule-Based Inference

Implement simple inference rules for synthetic fixtures.

Start with:

- Bank statement
- 1099-INT-like document
- Brokerage statement
- Mortgage statement

---

## Phase 4: Inspect Reports

Implement:

- Document completeness
- Entity listing
- Observation review queue
- Year-over-year gaps

---

## Phase 5: Multi-Currency and Jurisdiction

Add:

- Currency metadata
- Exchange rate table
- Jurisdiction metadata
- Base currency reporting

---

## Phase 6: Review Workflow

Implement:

- Accept observation
- Reject observation
- Mark needs review
- Link observation to entity

---

## Phase 7: UI Preparation

Stabilize APIs for future UI.

Expose:

- JSON reports
- Domain services
- Read-only dashboard endpoints if web UI is chosen

---

# 22. Codex Work Instructions

When using Codex, give it this instruction:

```text
Read docs/bankbuddy-financial-intelligence-architecture.md completely.

Do not implement immediately.

First inspect the existing BankBuddy codebase and produce an architecture review.

The goal is to evolve BankBuddy from a banking-focused app into the local-first financial intelligence platform described in the document.

Backward compatibility is not required.

Existing data can be discarded.

You may propose schema redesign, package restructuring, domain model redesign, and CLI redesign.

Produce the following first:

1. Current-state assessment
2. Gap analysis
3. Proposed target architecture
4. Proposed database schema
5. Proposed package/module structure
6. Proposed CLI design
7. Refactoring plan
8. Phased implementation roadmap

Wait for approval before changing code.
```

---

# 23. Open Design Questions

These should be resolved during implementation planning.

## 23.1 Document Storage

Should imported documents be:

- Referenced in place?
- Copied into managed storage?
- Both?

Recommendation:

Start with reference-in-place plus hash.
Add managed copy later.

---

## 23.2 AI Model Strategy

Should AI processing be:

- Local only?
- Optional remote LLM?
- Configurable?

Recommendation:

Start with rule-based inference.
Define interfaces for AI later.

---

## 23.3 UI Direction

Should the first UI be:

- CLI only?
- Local web?
- Native Swift?

Recommendation:

CLI first.
Then local web or Swift after domain model stabilizes.

---

## 23.4 Tax Rules

Should tax-specific rules be added?

Recommendation:

Only use tax documents as financial evidence initially.
Avoid tax advice and filing logic.

---

# 24. Final Product Direction

BankBuddy should become a trusted local financial intelligence system.

It should help users:

- Organize financial documents
- Understand their assets
- Understand their liabilities
- Track financial history
- Compare years
- Detect missing documents
- Detect new or missing accounts
- Understand multi-country financial relationships
- Preserve privacy

The core thesis:

> The user's financial life is a graph of documents, entities, observations, and relationships over time.

BankBuddy should model that graph clearly, locally, and safely.
