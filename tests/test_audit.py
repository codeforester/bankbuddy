from bankbuddy.accounts import Account
from bankbuddy.accounts import add_account
from bankbuddy.audit import audit_statement_coverage
from bankbuddy.audit import AuditFilterError
from bankbuddy.database import connect_database
from bankbuddy.paths import AppPaths
from bankbuddy.paths import resolve_app_paths


def add_boa_account(
    paths: AppPaths,
    *,
    account_number: str = "123456789",
    display_name: str | None = "Everyday Checking",
) -> Account:
    return add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number=account_number,
        account_type="checking",
        currency="USD",
        display_name=display_name,
    )


def add_statement(
    paths: AppPaths,
    account: Account,
    *,
    start_date: str,
    end_date: str,
    file_name: str | None = None,
) -> None:
    canonical_file_name = file_name or (
        f"bank-of-america_6789_{start_date}_{end_date}.pdf"
    )
    with connect_database(paths) as conn:
        bank_id = conn.execute(
            """
            select bank_id
            from accounts
            where account_id = ?
            """,
            (account.account_id,),
        ).fetchone()["bank_id"]
        cursor = conn.execute(
            """
            insert into import_files (
                file_name,
                file_hash,
                bank_id,
                original_file_name,
                canonical_file_name,
                processed_path,
                statement_start_date,
                statement_end_date,
                account_ref,
                source_format
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_file_name,
                f"hash-{account.account_id}-{canonical_file_name}",
                bank_id,
                canonical_file_name,
                canonical_file_name,
                f"processed/bank-of-america/2025/01/{canonical_file_name}",
                start_date,
                end_date,
                "6789",
                "boa_pdf",
            ),
        )
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                finished_at,
                rows_parsed,
                rows_imported
            ) values (?, ?, ?, ?, current_timestamp, ?, ?)
            """,
            (cursor.lastrowid, bank_id, account.account_id, "success", 1, 1),
        )
        conn.commit()


def finding_tuples(audits):
    return [
        (
            finding.status,
            finding.period_start.isoformat(),
            finding.period_end.isoformat(),
            finding.file_name,
        )
        for audit in audits
        for finding in audit.findings
    ]


def test_audit_statement_coverage_reports_continuous_periods(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    add_statement(paths, account, start_date="2025-01-01", end_date="2025-01-31")
    add_statement(paths, account, start_date="2025-02-01", end_date="2025-02-28")

    audits = audit_statement_coverage(
        paths,
        date_from="2025-01-01",
        date_to="2025-02-28",
    )

    assert len(audits) == 1
    assert audits[0].account_display == "Everyday Checking"
    assert audits[0].bank_name == "Bank of America"
    assert finding_tuples(audits) == [
        (
            "covered",
            "2025-01-01",
            "2025-01-31",
            "bank-of-america_6789_2025-01-01_2025-01-31.pdf",
        ),
        (
            "covered",
            "2025-02-01",
            "2025-02-28",
            "bank-of-america_6789_2025-02-01_2025-02-28.pdf",
        ),
    ]


def test_audit_statement_coverage_reports_missing_gaps(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    add_statement(paths, account, start_date="2025-01-10", end_date="2025-01-20")

    audits = audit_statement_coverage(
        paths,
        date_from="2025-01-01",
        date_to="2025-01-31",
    )

    assert finding_tuples(audits) == [
        ("missing", "2025-01-01", "2025-01-09", None),
        (
            "covered",
            "2025-01-10",
            "2025-01-20",
            "bank-of-america_6789_2025-01-10_2025-01-20.pdf",
        ),
        ("missing", "2025-01-21", "2025-01-31", None),
    ]


def test_audit_statement_coverage_reports_overlaps(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    add_statement(paths, account, start_date="2025-01-01", end_date="2025-01-31")
    add_statement(paths, account, start_date="2025-01-20", end_date="2025-02-28")

    audits = audit_statement_coverage(
        paths,
        date_from="2025-01-01",
        date_to="2025-02-28",
    )

    assert finding_tuples(audits) == [
        (
            "covered",
            "2025-01-01",
            "2025-01-31",
            "bank-of-america_6789_2025-01-01_2025-01-31.pdf",
        ),
        (
            "overlap",
            "2025-01-20",
            "2025-01-31",
            "bank-of-america_6789_2025-01-20_2025-02-28.pdf",
        ),
        (
            "covered",
            "2025-02-01",
            "2025-02-28",
            "bank-of-america_6789_2025-01-20_2025-02-28.pdf",
        ),
    ]


def test_audit_statement_coverage_reports_duplicate_periods(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    add_statement(paths, account, start_date="2025-01-01", end_date="2025-01-31")
    add_statement(
        paths,
        account,
        start_date="2025-01-01",
        end_date="2025-01-31",
        file_name="bank-of-america_6789_2025-01-01_2025-01-31-copy.pdf",
    )

    audits = audit_statement_coverage(
        paths,
        date_from="2025-01-01",
        date_to="2025-01-31",
    )

    assert finding_tuples(audits) == [
        (
            "covered",
            "2025-01-01",
            "2025-01-31",
            "bank-of-america_6789_2025-01-01_2025-01-31.pdf",
        ),
        (
            "duplicate",
            "2025-01-01",
            "2025-01-31",
            "bank-of-america_6789_2025-01-01_2025-01-31-copy.pdf",
        ),
    ]


def test_audit_statement_coverage_audits_years_independently(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    add_statement(paths, account, start_date="2024-01-01", end_date="2024-12-31")
    add_statement(paths, account, start_date="2025-01-01", end_date="2025-12-31")

    audits = audit_statement_coverage(paths, years=[2024, 2025])

    assert [(audit.window_start.isoformat(), audit.window_end.isoformat()) for audit in audits] == [
        ("2024-01-01", "2024-12-31"),
        ("2025-01-01", "2025-12-31"),
    ]
    assert [finding.status for audit in audits for finding in audit.findings] == [
        "covered",
        "covered",
    ]


def test_audit_statement_coverage_filters_by_account_last4(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    first_account = add_boa_account(paths, account_number="123456789")
    second_account = add_boa_account(
        paths,
        account_number="555550001",
        display_name="Savings",
    )
    add_statement(paths, first_account, start_date="2025-01-01", end_date="2025-01-31")
    add_statement(paths, second_account, start_date="2025-02-01", end_date="2025-02-28")

    audits = audit_statement_coverage(
        paths,
        account_last4="0001",
        date_from="2025-02-01",
        date_to="2025-02-28",
    )

    assert len(audits) == 1
    assert audits[0].account_id == second_account.account_id
    assert audits[0].account_display == "Savings"


def test_audit_statement_coverage_rejects_ambiguous_account_last4(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    add_boa_account(paths, account_number="123456789")
    add_boa_account(paths, account_number="999996789", display_name="Other")

    try:
        audit_statement_coverage(
            paths,
            account_last4="6789",
            date_from="2025-01-01",
            date_to="2025-01-31",
        )
    except AuditFilterError as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("Expected AuditFilterError")
