"""Repair helpers for historical import data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import sqlite3

from bankbuddy.database import connect_database
from bankbuddy.database import initialize_database
from bankbuddy.imports import extract_pdf_text
from bankbuddy.imports import normalize_description
from bankbuddy.imports import parse_boa_pdf_text
from bankbuddy.imports import ParsedTransaction
from bankbuddy.imports import transaction_hash
from bankbuddy.paths import AppPaths


RepairStatus = Literal["changed", "unchanged", "failed"]


@dataclass(frozen=True)
class BofaPdfRepairFileResult:
    """Repair result for one imported Bank of America PDF file/account pair."""

    file_id: int
    account_id: int
    file_name: str
    status: RepairStatus
    rows_parsed: int
    hashes_updated: int
    rows_inserted: int
    attempts_updated: int
    message: str | None = None


@dataclass(frozen=True)
class BofaPdfRepairSummary:
    """Aggregated repair result for Bank of America PDF imports."""

    dry_run: bool
    results: list[BofaPdfRepairFileResult]

    @property
    def files_scanned(self) -> int:
        """Return the number of file/account pairs inspected."""

        return len(self.results)

    @property
    def files_changed(self) -> int:
        """Return the number of file/account pairs with planned or applied changes."""

        return sum(1 for result in self.results if result.status == "changed")

    @property
    def files_failed(self) -> int:
        """Return the number of file/account pairs that could not be repaired."""

        return sum(1 for result in self.results if result.status == "failed")

    @property
    def hashes_updated(self) -> int:
        """Return transaction rows whose legacy hashes need repair."""

        return sum(result.hashes_updated for result in self.results)

    @property
    def rows_inserted(self) -> int:
        """Return missing transaction rows inserted or planned."""

        return sum(result.rows_inserted for result in self.results)

    @property
    def attempts_updated(self) -> int:
        """Return import attempts whose row counts need repair."""

        return sum(result.attempts_updated for result in self.results)


@dataclass(frozen=True)
class RepairTarget:
    """Imported BofA PDF file/account pair eligible for repair."""

    file_id: int
    account_id: int
    file_name: str
    processed_path: str


@dataclass(frozen=True)
class TransactionUpdate:
    """A transaction row update planned by repair."""

    transaction_id: int
    description: str
    normalized_description: str
    transaction_hash: str


@dataclass(frozen=True)
class TransactionInsert:
    """A missing transaction row planned by repair."""

    parsed: ParsedTransaction
    transaction_hash: str


@dataclass(frozen=True)
class AttemptUpdate:
    """An import attempt row-count update planned by repair."""

    attempt_id: int
    rows_parsed: int
    rows_imported: int
    rows_skipped_duplicate: int


@dataclass(frozen=True)
class RepairPlan:
    """A planned repair for one imported BofA PDF file/account pair."""

    target: RepairTarget
    rows_parsed: int
    transaction_updates: list[TransactionUpdate]
    transaction_inserts: list[TransactionInsert]
    attempt_updates: list[AttemptUpdate]


def repair_boa_pdf_imports(paths: AppPaths, *, dry_run: bool) -> BofaPdfRepairSummary:
    """Repair historical Bank of America PDF imports after hash-shape changes."""

    initialize_database(paths)
    results: list[BofaPdfRepairFileResult] = []
    with connect_database(paths) as conn:
        targets = list_boa_pdf_repair_targets(conn)
        category_id = uncategorized_category_id(conn)
        for target in targets:
            try:
                plan = plan_boa_pdf_repair(conn, paths, target)
            except (OSError, sqlite3.Error, ValueError) as exc:
                results.append(
                    BofaPdfRepairFileResult(
                        file_id=target.file_id,
                        account_id=target.account_id,
                        file_name=target.file_name,
                        status="failed",
                        rows_parsed=0,
                        hashes_updated=0,
                        rows_inserted=0,
                        attempts_updated=0,
                        message=str(exc),
                    )
                )
                continue

            if not dry_run:
                apply_boa_pdf_repair(conn, plan, category_id=category_id)
            status: RepairStatus = (
                "changed" if has_repair_changes(plan) else "unchanged"
            )
            results.append(
                BofaPdfRepairFileResult(
                    file_id=target.file_id,
                    account_id=target.account_id,
                    file_name=target.file_name,
                    status=status,
                    rows_parsed=plan.rows_parsed,
                    hashes_updated=len(plan.transaction_updates),
                    rows_inserted=len(plan.transaction_inserts),
                    attempts_updated=len(plan.attempt_updates),
                )
            )
        if not dry_run:
            conn.commit()
    return BofaPdfRepairSummary(dry_run=dry_run, results=results)


def list_boa_pdf_repair_targets(conn: sqlite3.Connection) -> list[RepairTarget]:
    """Return imported BofA PDF file/account pairs that have transaction rows."""

    rows = conn.execute(
        """
        select
            import_files.file_id,
            transactions.account_id,
            coalesce(
                import_files.canonical_file_name,
                import_files.file_name
            ) as file_name,
            import_files.processed_path
        from import_files
        join transactions using (file_id)
        join accounts on accounts.account_id = transactions.account_id
        join banks on banks.bank_id = accounts.bank_id
        where import_files.source_format = 'boa_pdf'
          and import_files.processed_path is not null
          and banks.bank_name = 'Bank of America'
        group by
            import_files.file_id,
            transactions.account_id,
            file_name,
            import_files.processed_path
        order by import_files.statement_end_date, import_files.file_id
        """
    ).fetchall()
    return [
        RepairTarget(
            file_id=int(row["file_id"]),
            account_id=int(row["account_id"]),
            file_name=row["file_name"],
            processed_path=row["processed_path"],
        )
        for row in rows
    ]


def plan_boa_pdf_repair(
    conn: sqlite3.Connection,
    paths: AppPaths,
    target: RepairTarget,
) -> RepairPlan:
    """Build a repair plan for one BofA PDF file/account pair."""

    processed_path = paths.root / target.processed_path
    parsed_rows = parse_boa_pdf_text(extract_pdf_text(processed_path))
    existing_by_source = existing_transactions_by_source_row(conn, target)
    transaction_updates: list[TransactionUpdate] = []
    transaction_inserts: list[TransactionInsert] = []

    for parsed in parsed_rows:
        repaired_hash = transaction_hash(parsed, source_format="boa_pdf")
        existing = existing_by_source.get(parsed.source_row_key)
        if existing is None:
            owner_id = transaction_hash_owner(
                conn,
                account_id=target.account_id,
                transaction_hash=repaired_hash,
            )
            if owner_id is None:
                transaction_inserts.append(
                    TransactionInsert(
                        parsed=parsed,
                        transaction_hash=repaired_hash,
                    )
                )
            continue

        validate_existing_transaction(target, parsed, existing)
        owner_id = transaction_hash_owner(
            conn,
            account_id=target.account_id,
            transaction_hash=repaired_hash,
        )
        transaction_id = int(existing["transaction_id"])
        if owner_id is not None and owner_id != transaction_id:
            raise ValueError(
                f"Repaired hash for source row {parsed.source_row_key} "
                f"already belongs to transaction {owner_id}."
            )
        normalized_description = normalize_description(parsed.description)
        if (
            existing["description"] != parsed.description
            or existing["normalized_description"] != normalized_description
            or existing["transaction_hash"] != repaired_hash
        ):
            transaction_updates.append(
                TransactionUpdate(
                    transaction_id=transaction_id,
                    description=parsed.description,
                    normalized_description=normalized_description,
                    transaction_hash=repaired_hash,
                )
            )

    attempt_updates = plan_attempt_updates(
        conn,
        target,
        rows_parsed=len(parsed_rows),
    )
    return RepairPlan(
        target=target,
        rows_parsed=len(parsed_rows),
        transaction_updates=transaction_updates,
        transaction_inserts=transaction_inserts,
        attempt_updates=attempt_updates,
    )


def existing_transactions_by_source_row(
    conn: sqlite3.Connection,
    target: RepairTarget,
) -> dict[str, sqlite3.Row]:
    """Return existing transactions keyed by source row for one file/account."""

    rows = conn.execute(
        """
        select
            transaction_id,
            transaction_date,
            amount_minor_units,
            description,
            normalized_description,
            source_row_key,
            transaction_hash
        from transactions
        where file_id = ?
          and account_id = ?
          and source_row_key is not null
        """,
        (target.file_id, target.account_id),
    ).fetchall()
    by_source: dict[str, sqlite3.Row] = {}
    for row in rows:
        source_row_key = row["source_row_key"]
        if source_row_key in by_source:
            raise ValueError(
                f"Multiple transactions use source row {source_row_key}."
            )
        by_source[source_row_key] = row
    return by_source


def validate_existing_transaction(
    target: RepairTarget,
    parsed: ParsedTransaction,
    existing: sqlite3.Row,
) -> None:
    """Validate that an existing row is the same statement row before repair."""

    if (
        existing["transaction_date"] != parsed.transaction_date
        or int(existing["amount_minor_units"]) != parsed.amount_minor_units
    ):
        raise ValueError(
            f"Existing transaction for file {target.file_id} source row "
            f"{parsed.source_row_key} does not match the reparsed statement row."
        )


def transaction_hash_owner(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    transaction_hash: str,
) -> int | None:
    """Return the owner transaction id for an account/hash pair."""

    row = conn.execute(
        """
        select transaction_id
        from transactions
        where account_id = ?
          and transaction_hash = ?
        """,
        (account_id, transaction_hash),
    ).fetchone()
    if row is None:
        return None
    return int(row["transaction_id"])


def plan_attempt_updates(
    conn: sqlite3.Connection,
    target: RepairTarget,
    *,
    rows_parsed: int,
) -> list[AttemptUpdate]:
    """Return successful import attempts whose summary counts need repair."""

    rows = conn.execute(
        """
        select
            attempt_id,
            rows_parsed,
            rows_imported,
            rows_skipped_duplicate
        from import_attempts
        where file_id = ?
          and account_id = ?
          and import_status = 'success'
          and rows_imported > 0
        """,
        (target.file_id, target.account_id),
    ).fetchall()
    updates: list[AttemptUpdate] = []
    for row in rows:
        if (
            int(row["rows_parsed"]) != rows_parsed
            or int(row["rows_imported"]) != rows_parsed
            or int(row["rows_skipped_duplicate"]) != 0
        ):
            updates.append(
                AttemptUpdate(
                    attempt_id=int(row["attempt_id"]),
                    rows_parsed=rows_parsed,
                    rows_imported=rows_parsed,
                    rows_skipped_duplicate=0,
                )
            )
    return updates


def apply_boa_pdf_repair(
    conn: sqlite3.Connection,
    plan: RepairPlan,
    *,
    category_id: int,
) -> None:
    """Apply one BofA PDF repair plan."""

    for update in plan.transaction_updates:
        conn.execute(
            """
            update transactions
            set description = ?,
                normalized_description = ?,
                transaction_hash = ?,
                updated_at = current_timestamp
            where transaction_id = ?
            """,
            (
                update.description,
                update.normalized_description,
                update.transaction_hash,
                update.transaction_id,
            ),
        )
    for insert in plan.transaction_inserts:
        parsed = insert.parsed
        conn.execute(
            """
            insert into transactions (
                account_id,
                category_id,
                file_id,
                transaction_date,
                amount_minor_units,
                currency,
                description,
                normalized_description,
                check_number,
                source_row_key,
                transaction_hash,
                transfer_status
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.target.account_id,
                category_id,
                plan.target.file_id,
                parsed.transaction_date,
                parsed.amount_minor_units,
                "USD",
                parsed.description,
                parsed.normalized_description,
                parsed.check_number,
                parsed.source_row_key,
                insert.transaction_hash,
                "none",
            ),
        )
    for update in plan.attempt_updates:
        conn.execute(
            """
            update import_attempts
            set rows_parsed = ?,
                rows_imported = ?,
                rows_skipped_duplicate = ?,
                updated_at = current_timestamp
            where attempt_id = ?
            """,
            (
                update.rows_parsed,
                update.rows_imported,
                update.rows_skipped_duplicate,
                update.attempt_id,
            ),
        )


def has_repair_changes(plan: RepairPlan) -> bool:
    """Return whether a repair plan contains any changes."""

    return bool(
        plan.transaction_updates
        or plan.transaction_inserts
        or plan.attempt_updates
    )


def uncategorized_category_id(conn: sqlite3.Connection) -> int:
    """Return the built-in Uncategorized category id."""

    row = conn.execute(
        "select category_id from categories where category_name = ?",
        ("Uncategorized",),
    ).fetchone()
    if row is None:
        raise ValueError("Built-in Uncategorized category is missing.")
    return int(row["category_id"])
