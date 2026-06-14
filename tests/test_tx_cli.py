from click.testing import CliRunner

from bankbuddy.accounts import add_account
from bankbuddy.cli import main
from bankbuddy.database import connect_database
from bankbuddy.imports import import_boa_csv
from bankbuddy.imports import parse_boa_pdf_text
from bankbuddy.imports import transaction_hash
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
"""

BOA_PDF_TEXT = """
Bank of America
Account number 1234 5678 901145
Statement Period: January 1, 2026 through January 31, 2026
Transaction activity
Date Description Amount
01/20/26 COFFEE SHOP -4.25
01/21/26 PAYROLL 2500.00
"""


def seed_transactions(tmp_path):
    home = tmp_path / "home"
    paths = resolve_app_paths(home)
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
        display_name="Everyday Checking",
    )
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    import_boa_csv(paths, csv_path, account_id=account.account_id)
    return home, account


def seed_duplicate_pdf_attempt(tmp_path):
    home = tmp_path / "home"
    paths = resolve_app_paths(home)
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="12345678901145",
        account_type="checking",
        currency="USD",
        display_name="Everyday Checking",
    )
    processed_path = (
        "processed/bank-of-america/2026/01/"
        "bank-of-america_1145_2026-01-01_2026-01-31.pdf"
    )
    (paths.root / processed_path).parent.mkdir(parents=True, exist_ok=True)
    (paths.root / processed_path).write_bytes(b"%PDF-1.4 placeholder")
    parsed_rows = parse_boa_pdf_text(BOA_PDF_TEXT)
    with connect_database(paths) as conn:
        bank_id = conn.execute(
            "select bank_id from banks where bank_name = ?",
            ("Bank of America",),
        ).fetchone()["bank_id"]
        category_id = conn.execute(
            "select category_id from categories where category_name = ?",
            ("Uncategorized",),
        ).fetchone()["category_id"]
        cursor = conn.execute(
            """
            insert into import_files (
                file_name,
                file_hash,
                bank_id,
                original_file_name,
                canonical_file_name,
                source_path,
                processed_path,
                statement_start_date,
                statement_end_date,
                account_ref,
                source_format,
                last_success_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "statement.pdf",
                "file-hash-1",
                bank_id,
                "statement.pdf",
                "bank-of-america_1145_2026-01-01_2026-01-31.pdf",
                "/downloads/statement.pdf",
                processed_path,
                "2026-01-01",
                "2026-01-31",
                "1145",
                "boa_pdf",
                "2026-06-14 10:00:00",
            ),
        )
        file_id = int(cursor.lastrowid)
        for parsed in parsed_rows:
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
                    source_row_key,
                    transaction_hash,
                    transfer_status,
                    created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account.account_id,
                    category_id,
                    file_id,
                    parsed.transaction_date,
                    parsed.amount_minor_units,
                    "USD",
                    parsed.description,
                    parsed.normalized_description,
                    parsed.source_row_key,
                    transaction_hash(parsed, source_format="boa_pdf"),
                    "none",
                    "2026-06-14 10:00:00",
                ),
            )
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                started_at,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate
            ) values (?, ?, ?, 'success', ?, ?, 2, 2, 0)
            """,
            (
                file_id,
                bank_id,
                account.account_id,
                "2026-06-14 10:00:00",
                "2026-06-14 10:00:01",
            ),
        )
        duplicate_cursor = conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                started_at,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate
            ) values (?, ?, ?, 'success', ?, ?, 2, 0, 2)
            """,
            (
                file_id,
                bank_id,
                account.account_id,
                "2026-06-14 11:00:00",
                "2026-06-14 11:00:01",
            ),
        )
        duplicate_attempt_id = int(duplicate_cursor.lastrowid)
        conn.commit()
    return home, duplicate_attempt_id


def test_tx_list_outputs_imported_transactions(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "ID | Date       | Account" in result.output
    assert "---+" in result.output
    assert "ID  Date" not in result.output
    assert " 1 | 2026-06-10 | Everyday Checking |   -4.25 | USD" in (
        result.output
    )
    assert " 2 | 2026-06-11 | Everyday Checking | 2500.00 | USD" in (
        result.output
    )
    assert "123456789" not in result.output


def test_tx_list_filters_by_account_id_and_date_range(tmp_path) -> None:
    home, account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        [
            "tx",
            "list",
            "--account-id",
            str(account.account_id),
            "--from",
            "2026-06-11",
            "--to",
            "2026-06-11",
        ],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "PAYROLL" in result.output
    assert "COFFEE SHOP" not in result.output


def test_tx_list_filters_by_debit_direction(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--direction", "debit"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" not in result.output


def test_tx_list_filters_by_credit_direction(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--direction", "credit"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "PAYROLL" in result.output
    assert "COFFEE SHOP" not in result.output


def test_tx_list_filters_by_bank_name(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--bank", "bank of america"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output


def test_tx_list_filters_by_currency(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--currency", "usd"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output


def test_category_list_outputs_seeded_categories(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["category", "list"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "Name            | Kind    | System" in result.output
    assert "Groceries" in result.output
    assert "Uncategorized" in result.output


def test_tx_categorize_updates_transaction_category(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    categorize_result = CliRunner().invoke(
        main,
        ["tx", "categorize", "1", "Groceries"],
        env={"BANKBUDDY_HOME": str(home)},
    )
    list_result = CliRunner().invoke(
        main,
        ["tx", "list", "--category", "Groceries"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert categorize_result.exit_code == 0
    assert "Updated transaction 1 category to Groceries." in categorize_result.output
    assert list_result.exit_code == 0
    assert "COFFEE SHOP" in list_result.output
    assert "PAYROLL" not in list_result.output
    assert "Groceries" in list_result.output


def test_tx_list_filters_uncategorized_transactions(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)
    runner = CliRunner()
    runner.invoke(
        main,
        ["tx", "categorize", "1", "Groceries"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    result = runner.invoke(
        main,
        ["tx", "list", "--uncategorized"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "PAYROLL" in result.output
    assert "COFFEE SHOP" not in result.output
    assert "Uncategorized" in result.output


def test_tx_categorize_rejects_unknown_category(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "categorize", "1", "Made Up"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 1
    assert "Category not found: Made Up" in result.output


def test_tx_list_rejects_category_and_uncategorized_together(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--category", "Groceries", "--uncategorized"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 1
    assert "Use either --category or --uncategorized, not both" in result.output


def test_tx_list_filters_by_account_number(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--account-number", "123 456 789"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output
    assert "123456789" not in result.output


def test_tx_list_filters_by_account_last4(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--account-last4", "6789"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output


def test_tx_list_rejects_missing_account_last4(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--account-last4", "0000"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "No account matches last four digits: 0000." in result.output


def test_tx_list_rejects_ambiguous_account_last4(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)
    paths = resolve_app_paths(home)
    add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="987656789",
        account_type="checking",
        currency="USD",
        display_name="Other Checking",
    )

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--account-last4", "6789"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "Account last four digits are ambiguous: 6789." in result.output


def test_tx_list_sorts_by_amount_descending(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--sort", "amount:desc"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert result.output.index("PAYROLL") < result.output.index("COFFEE SHOP")


def test_tx_list_uses_global_sort_order(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--sort", "date", "--order", "desc"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert result.output.index("PAYROLL") < result.output.index("COFFEE SHOP")


def test_tx_list_rejects_invalid_sort_field(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--sort", "posted_at"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "Unsupported sort field" in result.output


def test_tx_list_outputs_compact_view(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--view", "compact"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Date       |  Amount | Currency | Description" in result.output
    assert "2026-06-10 |   -4.25 | USD" in result.output
    assert "Everyday Checking" not in result.output


def test_tx_list_outputs_ledger_view(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--view", "ledger"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "ID | Date       | Account" in result.output
    assert "Type   |  Amount | Currency | Category      | Description" in (
        result.output
    )
    assert " 1 | 2026-06-10 | Everyday Checking | debit" in (
        result.output
    )
    assert " 2 | 2026-06-11 | Everyday Checking | credit | 2500.00" in (
        result.output
    )


def test_tx_list_outputs_summary(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--summary"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    lines = result.output.splitlines()
    summary_index = lines.index("Summary")
    assert lines[summary_index : summary_index + 4] == [
        "Summary",
        "Currency | Transactions | Debits | Credits |     Net",
        "---------+--------------+--------+---------+--------",
        "USD      |            2 |  -4.25 | 2500.00 | 2495.75",
    ]


def test_tx_list_summary_respects_direction_filter(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--direction", "debit", "--summary"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "USD      |            1 |  -4.25 |    0.00 | -4.25" in (
        result.output
    )
    assert "PAYROLL" not in result.output


def test_tx_list_outputs_csv_format(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--format", "csv"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "id,date,account,amount,currency,category,description",
        "1,2026-06-10,Everyday Checking,-4.25,USD,Uncategorized,COFFEE SHOP",
        "2,2026-06-11,Everyday Checking,2500.00,USD,Uncategorized,PAYROLL",
    ]


def test_tx_list_outputs_tsv_format_with_ledger_view(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--view", "ledger", "--format", "tsv"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "id\tdate\taccount\ttype\tamount\tcurrency\tcategory\tdescription",
        (
            "1\t2026-06-10\tEveryday Checking\tdebit\t-4.25\tUSD\t"
            "Uncategorized\tCOFFEE SHOP"
        ),
        (
            "2\t2026-06-11\tEveryday Checking\tcredit\t2500.00\tUSD\t"
            "Uncategorized\tPAYROLL"
        ),
    ]


def test_tx_list_rejects_summary_for_csv_format(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--format", "csv", "--summary"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "--summary is only supported with --format pretty" in result.output


def test_tx_list_reports_empty_state(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["tx", "list"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "No transactions found." in result.output


def test_tx_list_rejects_invalid_dates(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["tx", "list", "--from", "06/11/2026"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "Invalid date" in result.output


def test_tx_duplicates_outputs_reconstructed_duplicate_rows(
    tmp_path,
    monkeypatch,
) -> None:
    home, duplicate_attempt_id = seed_duplicate_pdf_attempt(tmp_path)
    monkeypatch.setattr(
        "bankbuddy.duplicate_diagnostics.extract_pdf_text",
        lambda _path: BOA_PDF_TEXT,
    )

    result = CliRunner().invoke(
        main,
        ["tx", "duplicates"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Attempt | Bank            | Account" in result.output
    assert f"{duplicate_attempt_id} | Bank of America | Everyday Checking" in (
        result.output
    )
    assert "2026-01-01 to 2026-01-31" in result.output
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output
    assert "Original ID" in result.output


def test_tx_duplicates_filters_by_attempt_and_year(tmp_path, monkeypatch) -> None:
    home, duplicate_attempt_id = seed_duplicate_pdf_attempt(tmp_path)
    monkeypatch.setattr(
        "bankbuddy.duplicate_diagnostics.extract_pdf_text",
        lambda _path: BOA_PDF_TEXT,
    )

    result = CliRunner().invoke(
        main,
        [
            "tx",
            "duplicates",
            "--attempt-id",
            str(duplicate_attempt_id),
            "--year",
            "2026",
        ],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output


def test_tx_duplicates_reports_empty_state(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["tx", "duplicates"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "No duplicate transactions found." in result.output
