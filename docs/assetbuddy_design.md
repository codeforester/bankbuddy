# AssetBuddy — Design, Architecture & Roadmap

**Version:** 1.0
**Status:** Design phase — ready for architecture refinement and implementation
**Evolved from:** BankBuddy (bank-focused CLI, transaction tracking)
**Date:** June 2026

---

## 1. What Is AssetBuddy?

AssetBuddy is a **document-first, privacy-first personal financial command center** for
technically capable individuals. It tracks every dimension of a person's financial life —
bank accounts, investments, properties, tax documents, employer records — across multiple
currencies and jurisdictions, without ever connecting to a bank or external institution.

### The Core Insight

Most personal finance tools (Mint, Personal Capital, Quicken) work by connecting to your
bank via OAuth and pulling data automatically. This creates:

- Privacy exposure — your credentials or tokens live on a third-party server
- Dependency — when the service shuts down (as Mint did in 2023), your data and
  history disappear
- Complexity — maintaining connections to dozens of institutions is hard engineering
- Fragility — any API change at any bank breaks the product

AssetBuddy takes the opposite approach: **the user provides all data manually by
downloading documents from institutions and feeding them to the system.** The system
makes meaning from those documents.

This is not a limitation — it is a feature. The target user is someone who:
- Knows how to log into their bank and download a statement
- Is comfortable running a CLI command
- Values data ownership and privacy over convenience
- Has a complex financial life (multiple countries, currencies, asset types)

---

## 2. Design Principles

### 1. Document-First
Every piece of data in the system comes from a document the user explicitly provides —
PDF, spreadsheet, or scanned image. No API connections. No OAuth. No automatic syncing.
The document is the source of truth.

### 2. Privacy by Design
No bank credentials stored. No cloud service holds financial data. Data lives locally on
the user's machine, with optional iCloud sync for family access. The threat model is
"someone gains access to your Mac" — not "a cloud server is breached."

### 3. Asset-Centric, Not Bank-Centric
The original BankBuddy was transaction-focused and bank-specific. AssetBuddy models
the complete financial picture: bank accounts, credit cards, mortgages, properties,
investment accounts, employer relationships, tax obligations. Every financial entity
is an **asset**.

### 4. Fail Loudly, Not Silently
If a document cannot be confidently routed to the correct asset, the system errors
out with a clear message rather than guessing. Bad data in the transactions table is
worse than a failed import.

### 5. Infer From Documents, Not From Manual Entry
The system should extract as much metadata as possible from the documents themselves —
institution name, account type, account suffix, date range, form type, jurisdiction.
The user's setup burden should be minimal.

### 6. Never Pollute the Transactions Table
All parsing and validation happens in a staging area. Only clean, validated,
deduplicated data is committed to `bb_transaction`. A bad import that rolls back
is infinitely better than corrupted transaction history.

### 7. All Computations On the Fly
No precomputed summaries or derived data stored in the database. Spending reports,
budget analysis, and trend computation all query raw transactions at runtime.
This keeps the schema clean and handles retroactive imports (historical data)
correctly without needing cache invalidation.

### 8. Multi-Currency, Multi-Jurisdiction by Default
No assumption that the user is in one country or uses one currency. Currency is
stored per transaction. Jurisdiction is stored per document and per asset. Budgets
are per-currency. The schema makes no US-centric or India-centric assumptions.

### 9. Households, Not Just Individuals
The design should accommodate joint accounts, family members with separate assets,
and shared financial visibility. This is deferred to a later phase but should not
be architecturally precluded.

### 10. Build for Yourself First
Ship when it works for you. Share when friends ask. Commercialize when strangers
want it. No premature scaling.

---

## 3. Evolution: BankBuddy → AssetBuddy

### What BankBuddy Already Has (Keep)

- Import pipeline: PDF and spreadsheet ingestion with file-level deduplication
  (SHA-256 hash of file contents)
- Row-level deduplication: SHA-256 hash of (asset + date + amount + description)
  prevents duplicate rows even from overlapping spreadsheets
- Staging area: parsed data validated in memory before committing to database
- Folder structure: `inbox/` for new files, `processed/<Institution>/` for
  archived files after import
- Bank inference from document content — not from filename
- Parsers: Bank of America (CSV, PDF), HDFC Bank (XLS), ICICI Bank (XLS),
  Apple Card (PDF)
- Transaction categorization: rule-based with user-correction learning
- Budget tracking: per category, per currency, monthly or annual
- CLI-first interface using `click`
- SQLite database (local)
- Base-managed project with `base_manifest.yaml`

### What Changes in AssetBuddy

- **Old model:** `bank` → `account` → `transaction`
- **New model:** `bb_institution` → `bb_asset` → `bb_transaction`
- Banks become institutions (broader concept)
- Accounts become assets (much broader: includes properties, mortgages, employer records)
- Documents become first-class entities (`bb_document`)
- Parsers are decoupled from assets and linked via a mapping table
- Fingerprinting introduced for routing documents to the correct asset
- Asset attributes stored in a flexible key-value table (`bb_asset_attribute`)

### What Stays the Same

- Design philosophy (document-first, local, private)
- Import flow (scan inbox, hash check, parse, validate, stage, commit, archive)
- Deduplication logic (file-level and row-level)
- Categorization engine (rule-based → ML → LLM fallback, phased)
- Budget design (per category, per currency, monthly/annual, min/max bounds)
- CLI-first development
- Python + SQLite + `click` stack

---

## 4. Naming Conventions

### Table Prefix
All tables prefixed with `bb_` to respect the BankBuddy origin and avoid
naming conflicts if the schema is embedded in a larger system.

### Table Names
All **singular** (not plural). `bb_asset`, not `bb_assets`.

### Full Table List
```
bb_institution
bb_asset_type
bb_asset
bb_asset_attribute_type
bb_asset_attribute
bb_asset_parser
bb_asset_to_parser
bb_document
bb_import_activity
bb_transaction
bb_category
bb_category_rule
bb_budget
bb_tax_source
bb_tax_profile
bb_tax_form_gap
```

---

## 5. Data Model

All tables include `created_at DATETIME NOT NULL` and `updated_at DATETIME NOT NULL`.

---

### `bb_institution`

Registry of all entities that issue documents or hold assets. Replaces the old
`banks` table but is much broader.

| Column | Type | Notes |
|---|---|---|
| `institution_id` | INTEGER PK | Surrogate key |
| `institution_name` | TEXT NOT NULL UNIQUE | "Bank of America", "Fidelity", "Apple Inc", "IRS", "Alameda County Assessor", "Bangalore City Corporation" |
| `institution_type` | TEXT NOT NULL | "bank", "brokerage", "employer", "government", "utility", "insurance", "other" |
| `country` | TEXT NOT NULL | "US", "India", "UK" — no country assumptions |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_asset_type`

Reference table defining valid asset types. Extensible — add new types as discovered.

| Column | Type | Notes |
|---|---|---|
| `asset_type_id` | INTEGER PK | Surrogate key |
| `asset_type_name` | TEXT NOT NULL UNIQUE | "bank_account", "credit_card", "investment_account", "mortgage_account", "property", "employer_record", "vehicle", "other" |
| `description` | TEXT | Human explanation of what this type represents |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Seed data:**
- `bank_account` — checking, savings, CD accounts
- `credit_card` — credit card accounts
- `investment_account` — brokerage, retirement (401k, IRA, NPS)
- `mortgage_account` — home loan accounts
- `property` — real estate (residential, rental, commercial, land)
- `employer_record` — W-2/salary slip source
- `vehicle` — car loans (future)
- `other` — catch-all for unclassified assets

---

### `bb_asset`

The unified root entity. Every financial entity the user tracks is a row here.

| Column | Type | Notes |
|---|---|---|
| `asset_id` | INTEGER PK | Surrogate key — universal key across the system |
| `asset_type_id` | INTEGER FK | References `bb_asset_type.asset_type_id` |
| `institution_id` | INTEGER FK | References `bb_institution.institution_id` |
| `asset_name` | TEXT NOT NULL | User-friendly label: "My BofA Checking", "Sunnyvale House", "Fidelity Brokerage" |
| `fingerprint_json` | TEXT | JSON metadata for document routing. Example: `{"holder_name":"Ramesh K", "account_suffix":"1234", "account_type":"checking"}` |
| `status` | TEXT NOT NULL | "active", "closed", "archived" |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Key design decision:** `asset_id` is the universal foreign key throughout the schema.
Transactions, documents, and import activities all reference `asset_id`, not a
bank-specific account ID.

---

### `bb_asset_attribute_type`

Whitelist of valid attribute types. Enforces consistency across all assets.
Extensible — add new types as you encounter them in documents.

| Column | Type | Notes |
|---|---|---|
| `attr_type_id` | INTEGER PK | Surrogate key |
| `attr_type_name` | TEXT NOT NULL UNIQUE | "account_number", "address", "email", "phone", "loan_number", "account_suffix", "holder_name", "property_type", "purchase_date", "purchase_price", "rental_days_per_year", "depreciation_basis", "tax_id", "employer_ein" |
| `description` | TEXT | What this attribute means |
| `applicable_asset_types` | TEXT | JSON array of asset types that typically have this attr. Null = applies to any |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_asset_attribute`

Flexible key-value store for asset-specific attributes.

| Column | Type | Notes |
|---|---|---|
| `attr_id` | INTEGER PK | Surrogate key |
| `asset_id` | INTEGER FK | References `bb_asset.asset_id` |
| `attr_type_id` | INTEGER FK | References `bb_asset_attribute_type.attr_type_id` |
| `attr_value` | TEXT NOT NULL | The actual value: "123 Main St, Sunnyvale CA", "me@email.com", "1234" (last 4 of account) |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Why this pattern instead of typed columns?**
Every asset type has different attributes. A bank account has an account number.
A property has an address and purchase date. A mortgage has a loan number and lender.
Rather than adding columns to `bb_asset` for every possible attribute (which bloats
the table and breaks for new asset types), we store attributes in a separate table.
Query: `SELECT attr_value FROM bb_asset_attribute a JOIN bb_asset_attribute_type t
ON a.attr_type_id = t.attr_type_id WHERE asset_id = 5 AND t.attr_type_name = 'address'`

---

### `bb_asset_parser`

Registry of available document parsers. A parser is a parsing strategy for a specific
document format — decoupled from any particular asset instance.

| Column | Type | Notes |
|---|---|---|
| `parser_id` | INTEGER PK | Surrogate key |
| `parser_name` | TEXT NOT NULL UNIQUE | "bof_a_checking_statement", "bof_a_savings_statement", "bof_a_mortgage_statement", "apple_card_statement", "hdfc_savings_xls", "icici_checking_xls", "form_1099_int", "form_1099_div", "form_w2", "property_tax_statement_ca", "property_tax_statement_india" |
| `asset_type_id` | INTEGER FK | Which asset type does this parser produce data for? |
| `institution_id` | INTEGER FK | Usually tied to one institution (nullable if format-generic) |
| `description` | TEXT | How to identify documents this parser handles |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_asset_to_parser`

Links an asset to one or more parsers. One asset can have multiple parsers
(e.g., BofA checking has both PDF and CSV parsers).

| Column | Type | Notes |
|---|---|---|
| `mapping_id` | INTEGER PK | Surrogate key |
| `asset_id` | INTEGER FK | References `bb_asset.asset_id` |
| `parser_id` | INTEGER FK | References `bb_asset_parser.parser_id` |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_document`

First-class entity. Every document the user feeds to the system — bank statement,
tax form, property tax bill, mortgage statement — is tracked here.

| Column | Type | Notes |
|---|---|---|
| `doc_id` | INTEGER PK | Surrogate key |
| `asset_id` | INTEGER FK | References `bb_asset.asset_id` — which asset does this belong to? Null if routing failed |
| `parser_id` | INTEGER FK | References `bb_asset_parser.parser_id` — which parser was used? |
| `doc_type` | TEXT NOT NULL | "bank_statement", "credit_card_statement", "1099_int", "1099_div", "1099_nec", "w2", "property_tax_statement", "mortgage_statement", "prior_tax_return", "salary_slip" |
| `jurisdiction` | TEXT | "US", "India", "UK" — for geographic and tax classification |
| `tax_year` | INTEGER | For tax documents: 2024, 2025, etc. |
| `file_name` | TEXT NOT NULL | Standardized name: `<Name>-<Year>-<Type>-<Institution>-<Suffix>.<ext>`. Example: `Ramesh-2025-1099INT-BofA-x1234.pdf` |
| `file_path` | TEXT NOT NULL | Local or iCloud path |
| `file_hash` | TEXT NOT NULL UNIQUE | SHA-256 of file contents — prevents re-importing same file |
| `fingerprint_json` | TEXT | Metadata extracted from document: `{"holder_name":"Ramesh K", "date_range":"2025-01-01/2025-01-31", "account_suffix":"1234", "total_amount":"5678.90"}` |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_import_activity`

Complete import history. Every import attempt is logged here — success or failure.

| Column | Type | Notes |
|---|---|---|
| `import_id` | INTEGER PK | Surrogate key |
| `doc_id` | INTEGER FK | References `bb_document.doc_id` — which document triggered this? |
| `asset_id` | INTEGER FK | References `bb_asset.asset_id` — where did the data go? |
| `parser_id` | INTEGER FK | References `bb_asset_parser.parser_id` — which parser was used? |
| `import_status` | TEXT NOT NULL | "success", "failed", "partial", "pending_review" |
| `rows_total` | INTEGER | Total rows parsed from document |
| `rows_imported` | INTEGER | New rows added to `bb_transaction` |
| `rows_duplicate` | INTEGER | Rows skipped as duplicates |
| `rows_error` | INTEGER | Rows that failed validation |
| `error_message` | TEXT | If status is "failed" or "partial" — why? |
| `import_date` | DATETIME NOT NULL | Timestamp of import attempt |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_transaction`

The heart of the system. Every financial transaction from every asset.

| Column | Type | Notes |
|---|---|---|
| `transaction_id` | INTEGER PK | Surrogate key |
| `asset_id` | INTEGER FK | References `bb_asset.asset_id` — which asset is this from? |
| `category_id` | INTEGER FK | References `bb_category.category_id` — defaults to Uncategorized |
| `import_id` | INTEGER FK | References `bb_import_activity.import_id` — which import brought this in? |
| `transaction_date` | DATE NOT NULL | |
| `amount` | REAL NOT NULL | Positive = inflow/credit. Negative = outflow/debit |
| `currency` | TEXT NOT NULL | "USD", "INR", "GBP" etc. — stored per transaction, not per asset |
| `description` | TEXT | Transaction remark from source document |
| `check_number` | TEXT | Optional |
| `transfer_pair_id` | TEXT | UUID linking two legs of an internal transfer between assets |
| `transaction_hash` | TEXT NOT NULL UNIQUE | SHA-256 of (asset_id + date + amount + currency + description) — row-level deduplication |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Key changes from BankBuddy:**
- `asset_id` instead of `account_id` — works for any asset type
- `currency` per transaction — a single asset could have multi-currency transactions
- `transfer_pair_id` links any two assets, not just bank accounts

---

### `bb_category`

| Column | Type | Notes |
|---|---|---|
| `category_id` | INTEGER PK | Surrogate key |
| `category_name` | TEXT NOT NULL UNIQUE | "Salary", "Groceries", "Travel", "Transfer", "Uncategorized" |
| `is_system` | BOOLEAN NOT NULL | System categories cannot be deleted |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Seed categories:**
Income: Salary, Interest, Dividends, Rental Income, Other Income
Expense: Groceries, Dining, Utilities, Travel, Healthcare, Shopping, Entertainment,
Education, Insurance, Rent/Mortgage, Property Tax, Other Expense
Special: Transfer (excluded from all reports), Uncategorized (fallback, undeletable)

---

### `bb_category_rule`

| Column | Type | Notes |
|---|---|---|
| `rule_id` | INTEGER PK | Surrogate key |
| `pattern` | TEXT NOT NULL | String or regex matched against transaction description |
| `category_id` | INTEGER FK | Target category |
| `priority` | INTEGER NOT NULL | Higher = wins over lower-priority rules |
| `is_user_defined` | BOOLEAN NOT NULL | True if created from a user correction |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_budget`

| Column | Type | Notes |
|---|---|---|
| `budget_id` | INTEGER PK | Surrogate key |
| `category_id` | INTEGER FK | References `bb_category.category_id` |
| `currency` | TEXT NOT NULL | "USD", "INR" etc. — budget is per-currency |
| `budget_type` | TEXT NOT NULL | "monthly" or "annual" — not both for same category+currency |
| `min_amount` | REAL | Optional lower bound |
| `max_amount` | REAL | Optional upper bound |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Unique constraint:** `(category_id, currency)` — one budget per category per currency.
Switching between monthly and annual requires deleting the old budget first.

---

### `bb_tax_source`

Inferred registry of entities expected to issue tax documents.

| Column | Type | Notes |
|---|---|---|
| `source_id` | INTEGER PK | Surrogate key |
| `asset_id` | INTEGER FK | References `bb_asset.asset_id` — which asset is this source linked to? |
| `source_name` | TEXT NOT NULL | "Fidelity Brokerage", "Bank of America Savings", "ACME Corp" |
| `source_type` | TEXT NOT NULL | "bank", "brokerage", "employer", "property", "other" |
| `expected_forms` | TEXT NOT NULL | JSON array: `["1099-INT", "1099-DIV"]` |
| `jurisdiction` | TEXT NOT NULL | "US", "India" |
| `active` | BOOLEAN NOT NULL | False if this relationship is closed/ended |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_tax_profile`

High-level snapshot of the user's tax situation per year.

| Column | Type | Notes |
|---|---|---|
| `profile_id` | INTEGER PK | Surrogate key |
| `tax_year` | INTEGER NOT NULL UNIQUE | e.g. 2025 |
| `filing_status` | TEXT | "single", "married_filing_jointly", "married_filing_separately" |
| `has_rental_property` | BOOLEAN | |
| `has_investments` | BOOLEAN | |
| `has_self_employment` | BOOLEAN | |
| `has_foreign_income` | BOOLEAN | Income from outside primary country |
| `jurisdictions` | TEXT | JSON array: `["US", "India"]` |
| `notes` | TEXT | Free text |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

### `bb_tax_form_gap`

Tracks expected tax forms and whether they've been received.

| Column | Type | Notes |
|---|---|---|
| `gap_id` | INTEGER PK | Surrogate key |
| `tax_year` | INTEGER NOT NULL | |
| `source_id` | INTEGER FK | References `bb_tax_source.source_id` |
| `expected_form_type` | TEXT NOT NULL | "1099-INT", "1099-DIV", "W-2", "1098", "property_tax_statement" |
| `expected_by_date` | DATE | Typical deadline for this form to arrive |
| `received_date` | DATE | Null if not yet received |
| `doc_id` | INTEGER FK | References `bb_document.doc_id` when received |
| `status` | TEXT NOT NULL | "pending", "received", "waived" |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

---

## 6. Document Routing — The Fingerprint System

This is the most important new architectural concept in AssetBuddy.

### Problem

Different documents identify the account/asset they belong to in different ways:
- Bank of America checking statement → contains full account number
- Apple Card statement → contains NO account number, not even last 4 digits
- Property tax statement → identified by property address + parcel number
- 1099-INT → identified by institution name + payer EIN + possibly account suffix

Without a smart routing mechanism, you can't know which `bb_asset` a document belongs to.

### Solution: Two-Level Routing

**Level 1: Parser identification**
Read the top portion of every document to identify which parser handles it.
Pattern match on known signatures:
- "Bank of America" + column headers → `bof_a_checking_statement`
- "Apple Card" + "Goldman Sachs" → `apple_card_statement`
- "Form 1099-INT" → `form_1099_int`
- "COUNTY OF SANTA CLARA" + "Secured Property Tax" → `property_tax_statement_ca`

**Level 2: Asset routing via fingerprint**
Once the parser is identified, look up `bb_asset_to_parser` to find candidate assets.

```
candidates = SELECT a.* FROM bb_asset a
             JOIN bb_asset_to_parser ap ON a.asset_id = ap.asset_id
             JOIN bb_asset_parser p ON ap.parser_id = p.parser_id
             WHERE p.parser_name = <identified_parser>
```

Then apply fingerprint matching:
- If exactly 1 candidate → route there (no fingerprint needed)
- If 0 candidates → error: "No asset configured for this parser"
- If multiple candidates → match document fingerprint against asset fingerprints

**Fingerprint matching logic:**
- Extract key fields from document: holder name, account suffix, address, date range, totals
- Compare against `bb_asset.fingerprint_json` for each candidate
- If exactly 1 match → route there
- If still ambiguous → error: "Multiple assets matched — please clarify"
- If no match → error: "No asset fingerprint matched — please update asset fingerprint"

### Fingerprint Examples

**BofA Checking:**
```json
{"holder_name": "Ramesh K", "account_suffix": "1234", "account_type": "checking"}
```

**Apple Card:**
```json
{"holder_name": "Ramesh K", "card_member_since": "2020"}
```

**Property Tax Statement:**
```json
{"parcel_number": "111-22-333", "property_address": "123 Main St, Sunnyvale CA 94087"}
```

**1099-INT:**
```json
{"payer_name": "Bank of America", "payer_ein": "94-1687665", "account_suffix": "1234"}
```

---

## 7. Import Flow

### Folder Structure
```
~/AssetBuddy/
├── inbox/               ← User drops all documents here
└── processed/
    ├── Bank of America/
    ├── Apple Card/
    ├── Fidelity/
    ├── Alameda County Assessor/
    └── IRS/
```

Subdirectories named after the institution. Created automatically on first import.

### Step-by-Step Import Process

1. **Scan `inbox/`** for new files (PDF or spreadsheet)
2. **Compute SHA-256 hash** of the file
3. **Check `bb_document.file_hash`** — if exists, skip with message: "Already imported"
4. **Identify parser** from document content — if not confident, fail loudly
5. **Extract document fingerprint** from document metadata
6. **Route to asset** using parser + fingerprint matching (see Section 6)
   - If routing fails (ambiguous or no match), log to `bb_import_activity` with
     status "failed" and leave file in inbox
7. **Decrypt PDF** if password-protected (password stored in `bb_asset_attribute`
   with `attr_type_name = "pdf_password"`)
8. **Parse document** using identified parser into staging area (in-memory)
9. **Validate staged data:**
   - Required fields present (date, amount, description)
   - Dates sensible (not future, not before 2000)
   - Amounts are numeric
   - No intra-batch duplicates
10. **Row-level deduplication:** Compute `transaction_hash` for each row.
    Skip rows where hash already exists in `bb_transaction`.
    Count and report skipped rows.
11. **Detect internal transfers:** Match debits and credits of same amount across
    assets within a 2-day window. Assign shared `transfer_pair_id` UUID.
12. **Auto-categorize** using `bb_category_rule` ordered by priority.
    Uncategorized → default "Uncategorized" category.
13. **Create `bb_document` record** with standardized filename and fingerprint
14. **Commit rows to `bb_transaction`** — only new, validated rows
15. **Create `bb_import_activity` record** with full summary
16. **Move original file** to `processed/<Institution Name>/`

### On Failure (Steps 4–11)
- Log to `bb_import_activity` with status "failed" and error message
- Do NOT write to `bb_transaction`
- Leave original file in `inbox/`
- Print clear error to user

### Import Summary Output
```
File: hdfc_savings_nov2025.pdf
Institution: HDFC Bank | Asset: My HDFC Savings | Parser: hdfc_savings_xls
Total rows parsed:      87
New rows imported:      54
Duplicate rows skipped: 33
Transfer pairs detected: 2
Categories assigned:    51 (3 Uncategorized)
```

---

## 8. Categorization Engine

### Phase 1: Rule-Based (Current)
- Match description against `bb_category_rule.pattern` ordered by `priority` descending
- Highest-priority matching rule wins
- No match → "Uncategorized"
- User manual override → auto-creates new rule with `is_user_defined = true`

### Phase 2: ML-Assisted (scikit-learn)
- TF-IDF vectorization of transaction descriptions
- Naive Bayes or Logistic Regression classifier
- Training data: accumulated user-corrected transactions (~300+ examples to start)
- Model serialized to local file via `joblib`
- Low-confidence → fall back to "Uncategorized" rather than guess
- Retrain periodically as corrections accumulate

### Phase 3: LLM Fallback
- Transactions below confidence threshold → call Claude API
- Send description + category list, get best match
- Handles novel/unusual descriptions gracefully

---

## 9. CLI Command Surface

### `asset-buddy` (or keep `bank-buddy` during transition)

```bash
# Import
asset-buddy import                        # Process all new files in inbox/
asset-buddy import --file FILE            # Import specific file
asset-buddy import --status               # Show import history
asset-buddy import --retry IMPORT_ID      # Retry a failed import

# Assets (replaces account management)
asset-buddy asset list                    # List all assets
asset-buddy asset add                     # Add asset (interactive)
asset-buddy asset show ASSET_ID           # Show asset details and attributes
asset-buddy asset set-attr ASSET_ID TYPE VALUE  # Set asset attribute
asset-buddy asset link-parser ASSET_ID PARSER   # Link parser to asset
asset-buddy asset deactivate ASSET_ID     # Mark asset as closed/archived

# Transactions
asset-buddy tx list                       # List recent transactions
asset-buddy tx list --asset ASSET_ID
asset-buddy tx list --from DATE --to DATE
asset-buddy tx list --category CATEGORY
asset-buddy tx list --currency USD
asset-buddy tx list --uncategorized
asset-buddy tx list --transfers
asset-buddy tx categorize TX_ID CATEGORY  # Override category

# Reporting
asset-buddy report spending --year YEAR
asset-buddy report spending --year YEAR --month M
asset-buddy report income --year YEAR
asset-buddy report trend --category CAT --years 3
asset-buddy report budget --year YEAR
asset-buddy report net-worth              # Total across all assets

# Budget
asset-buddy budget list
asset-buddy budget set CATEGORY CURRENCY TYPE MIN MAX
asset-buddy budget delete CATEGORY CURRENCY

# Categories
asset-buddy category list
asset-buddy category add NAME
asset-buddy category rules list
asset-buddy category rules add PATTERN CATEGORY PRIORITY
asset-buddy category train                # Retrain ML model

# Tax
asset-buddy tax import                    # Import tax documents from inbox/
asset-buddy tax profile --year YEAR       # Show inferred tax profile
asset-buddy tax gaps --year YEAR          # Show missing/pending forms
asset-buddy tax docs list --year YEAR
asset-buddy tax docs show DOC_ID
asset-buddy tax summary --year YEAR       # Full tax picture

# Setup
asset-buddy setup institution add         # Add new institution
asset-buddy setup parser list             # List available parsers
asset-buddy status                        # System overview
```

---

## 10. Product Positioning

### Who This Is For

**Primary user:** An engineer, accountant, or financially sophisticated person who:
- Has income or assets in more than one country
- Has multiple institution relationships (banks, brokerages, employer, properties)
- Values owning their data and doesn't want to share credentials with third parties
- Is comfortable downloading files and running commands
- Is frustrated with the complexity of tax season ("do I have all my 1099s?")

**Secondary user:** The non-technical spouse or family member who needs read-only
visibility via a web dashboard. They should never need to touch the CLI.

### What It Is NOT

- Not a Mint replacement for the general public
- Not a tax filing tool (it is a tax *preparation awareness* tool)
- Not a tool that connects to banks via API
- Not a cloud service
- Not an App Store product (at least not initially)

### Market Gap

No consumer product today:
1. Unifies banking + tax document awareness in one tool
2. Is document-centric rather than OAuth-based
3. Handles dual-jurisdiction (e.g. India + US) tax tracking for NRIs
4. Runs fully locally with zero cloud dependency
5. Covers all asset types (not just bank accounts)

---

## 11. Phased Roadmap

### Phase 0 — Migration: BankBuddy → AssetBuddy
- [ ] Rename tables to `bb_` prefix with new singular names
- [ ] Create `bb_institution`, `bb_asset_type`, `bb_asset`, `bb_asset_attribute_type`,
      `bb_asset_attribute` tables
- [ ] Create `bb_asset_parser` and `bb_asset_to_parser` tables
- [ ] Create `bb_document` and `bb_import_activity` tables
- [ ] Migrate existing BankBuddy data into new schema
- [ ] Update all existing parsers to work with new routing layer
- [ ] Update CLI commands to use asset-centric terminology
- [ ] Write migration script for existing users

### Phase 1 — AssetBuddy Core (CLI)
- [ ] Fingerprint-based document routing
- [ ] Support for all existing parsers (BofA, HDFC, ICICI, Apple Card)
- [ ] New parsers: mortgage statements, 1099-INT, 1099-DIV, W-2
- [ ] Property asset type with address, purchase price, rental days attributes
- [ ] Multi-currency transaction support
- [ ] Transfer detection between any two assets (not just bank accounts)
- [ ] Full CLI command surface as defined above
- [ ] Budget and categorization migrated to new schema

### Phase 2 — Tax Layer
- [ ] `bb_tax_source`, `bb_tax_profile`, `bb_tax_form_gap` tables
- [ ] Tax document ingestion and routing
- [ ] Tax profile inference from documents
- [ ] Gap detection: "You're missing 1099-DIV from Fidelity"
- [ ] Annual tax readiness summary
- [ ] India tax document support (Form 26AS, salary slips)
- [ ] `tax-buddy` CLI (or `asset-buddy tax` subcommands)

### Phase 3 — Intelligence & Automation
- [ ] ML-based categorization (scikit-learn)
- [ ] LLM fallback categorization (Claude API)
- [ ] File watcher daemon (`watchdog`) for auto-import
- [ ] macOS `launchd` integration for daemon at login
- [ ] macOS native notifications on import completion
- [ ] iCloud document storage for family sharing

### Phase 4 — Web Interface
- [ ] Read-only web dashboard (Node.js)
- [ ] Spending trends, income trends, net worth over time
- [ ] Budget vs actuals visualization
- [ ] Tax document status and gap view
- [ ] Multi-year trend views
- [ ] Accessible to non-technical family members
- [ ] Full management capability for primary user

### Phase 5 — Mobile & Beyond
- [ ] iOS app (local install via Xcode — not App Store initially)
- [ ] Read-only viewer: transactions, budgets, tax gaps
- [ ] Document upload from phone (drag documents from email)
- [ ] Multi-user / household support
- [ ] User authentication for web UI

---

## 12. Open Questions for Implementation

- [ ] **Migration strategy:** How do existing BankBuddy users migrate? Is there a
      `asset-buddy migrate` command that reads old schema and transforms it?
- [ ] **Household / multi-user:** Should `bb_asset` have an `owner_id` field now
      or is this deferred? Better to add it now than to bolt it on later.
- [ ] **Fingerprint storage format:** JSON in a single column vs separate
      `bb_asset_fingerprint` table. JSON is simpler; table is more queryable.
- [ ] **PDF password storage:** Currently plaintext in `bb_asset_attribute`.
      Future: encrypt using macOS Keychain.
- [ ] **iCloud path vs local path:** `bb_document.file_path` — should this be an
      abstract path (resolved at runtime) or an absolute path?
- [ ] **India tax document types:** Form 26AS, AIS, ITR acknowledgment — need
      parser definitions for these.
- [ ] **Property depreciation calculation:** How much does the app compute vs
      just store the inputs and let a tax professional handle it?
- [ ] **CLI naming:** Keep `bank-buddy` as the CLI name during transition, or
      rename to `asset-buddy` immediately?
- [ ] **AGPL v3 license:** All repos (base, bank-buddy, banyan-labs) to be
      relicensed from MIT to AGPL v3.

---

## 13. License

All AssetBuddy/BankBuddy code is (or will be) licensed under
**GNU Affero General Public License v3.0 (AGPL v3)**.

This means:
- Anyone can use, modify, and distribute the code
- If you modify it and run it as a network service, you must open source your changes
- Commercial use requires either complying with AGPL or negotiating a separate license

The author is the sole contributor. No external contributions complicate the
relicensing from MIT to AGPL v3.

---

*Document prepared June 2026. Ready for architecture review and phased implementation.*
