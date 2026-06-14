# Statement Coverage Audit Design

## Goal

Add a read-only statement coverage audit so users can sanity-check whether
imported statement files cover an expected date range for each account.

## Scope

The first version audits imported statement metadata, not balances. It uses
`import_files.statement_start_date`, `statement_end_date`, `account_ref`,
`source_format`, and the successful import attempts that tie files to accounts.
It reports missing gaps, overlapping periods, duplicate statement periods, and
covered periods for selected accounts.

The command is:

```text
bankbuddy audit statements
bankbuddy audit statements --years 2025
bankbuddy audit statements --years 2024,2025
bankbuddy audit statements --from 2025-01-01 --to 2025-12-31
bankbuddy audit statements --account-id 1 --years 2025
bankbuddy audit statements --account-last4 1145 --years 2025
```

`--years` and `--from/--to` are mutually exclusive. `--years` accepts a
comma-separated list of four-digit years and audits each requested calendar year
as an independent window. `--from` and `--to` define one continuous window and
must be provided together. If no date selector is provided, the audit window for
each account is its imported statement coverage range.

The initial account selectors are `--account-id` and `--account-last4`. The
last-four selector must resolve to exactly one configured account, matching the
transaction-list convention. `--bank` and full `--account-number` can be added
later if needed.

## Output

The default output is a human-readable table grouped by account and audit
window. Rows are sorted by account, window start, issue severity, and period
start. The command exits zero even when it finds gaps or overlaps; findings are
data-quality results, not command failures.

Example:

```text
Account  Bank             Window
...1145  Bank of America  2025-01-01 to 2025-12-31

Status     Period                      File
missing    2025-01-01 to 2025-01-21    -
covered    2025-01-22 to 2025-02-18    bank-of-america_1145_2025-01-22_2025-02-18.pdf
overlap    2025-02-18 to 2025-02-20    bank-of-america_1145_2025-02-18_2025-03-20.pdf
duplicate  2025-04-22 to 2025-05-19    bank-of-america_1145_2025-04-22_2025-05-19-fb17f027.pdf
```

## Rules

- Only successful import attempts with an `account_id` participate in the audit.
- Statement files missing start or end dates are ignored for coverage but can be
  reported later as metadata warnings.
- Coverage treats statement periods as inclusive dates.
- Adjacent periods are continuous when the next start date is the day after the
  prior end date.
- A missing segment is the uncovered span between the audit window cursor and
  the next statement start, clipped to the audit window.
- An overlap is the intersection between a statement period and previously
  covered dates in the same audit window.
- Duplicate periods are additional files for the same account with identical
  statement start and end dates. One row remains the covered row; later rows are
  duplicate findings.
- Statement periods that partially extend outside the audit window are clipped
  for reported covered/overlap periods, while the file name remains the original
  imported file.

## Components

- `src/bankbuddy/audit.py` owns statement coverage queries and period analysis.
- `tests/test_audit.py` covers the pure audit behavior and account/window
  selectors.
- `src/bankbuddy/cli.py` adds the `audit statements` command and pretty table
  rendering.
- `tests/test_audit_cli.py` covers command-line validation and display.
- README, changelog, and `bank_buddy_spec.md` document the command.

## Out Of Scope

- Opening/closing balance reconciliation.
- Inferring missing transactions from balances.
- Mutating import history or transactions.
- JSON, CSV, or TSV output for audit results.
