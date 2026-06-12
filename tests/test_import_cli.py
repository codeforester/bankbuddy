from click.testing import CliRunner

from bankbuddy.cli import main


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
"""

BOA_PDF_TEXT = """
Bank of America
Account number 1234 5678 901145
Statement Period: June 1, 2026 through June 30, 2026
Transaction activity
Date Description Amount Balance
06/10 COFFEE SHOP -4.25 100.00
06/11 PAYROLL 2,500.00 2,600.00
"""


def test_import_file_command_reports_summary(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}

    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    import_result = runner.invoke(
        main,
        ["import", "--file", str(csv_path), "--account-id", "1"],
        env=env,
    )

    assert add_result.exit_code == 0
    assert import_result.exit_code == 0
    assert "File: boa.csv" in import_result.output
    assert "Rows parsed: 2" in import_result.output
    assert "Rows imported: 2" in import_result.output
    assert "Duplicate rows skipped: 0" in import_result.output


def test_import_file_command_reports_duplicate_summary(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    first = runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)
    second = runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Rows imported: 0" in second.output
    assert "Duplicate rows skipped: 2" in second.output


def test_import_history_command_outputs_attempts(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    result = runner.invoke(main, ["import", "history"], env=env)

    assert result.exit_code == 0
    assert "ID  File  Bank  Status  Started  Finished  Parsed  Imported  Duplicates  Error" in (
        result.output
    )
    assert "2  boa.csv  Bank of America  success" in result.output
    assert "  2  0  2  -" in result.output
    assert "1  boa.csv  Bank of America  success" in result.output
    assert "  2  2  0  -" in result.output


def test_import_history_command_filters_by_status_and_limit(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    result = runner.invoke(
        main,
        ["import", "history", "--status", "success", "--limit", "1"],
        env=env,
    )

    assert result.exit_code == 0
    assert "2  boa.csv  Bank of America  success" in result.output
    assert "1  boa.csv  Bank of America  success" not in result.output


def test_import_history_command_reports_empty_state(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["import", "history"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "No import attempts found." in result.output


def test_import_file_command_routes_pdf_imports(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "boa.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic fixture placeholder")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    monkeypatch.setattr("bankbuddy.imports.extract_pdf_text", lambda _path: BOA_PDF_TEXT)

    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "12345678901145",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    import_result = runner.invoke(
        main,
        ["import", "--file", str(pdf_path), "--account-id", "1"],
        env=env,
    )

    assert add_result.exit_code == 0
    assert import_result.exit_code == 0
    assert "File: boa.pdf" in import_result.output
    assert "Rows parsed: 2" in import_result.output
    assert "Rows imported: 2" in import_result.output


def test_pdf_import_debug_log_omits_full_account_number(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "boa.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic fixture placeholder")
    log_path = tmp_path / "bank-buddy.log"
    runner = CliRunner()
    env = {
        "BANKBUDDY_HOME": str(tmp_path / "home"),
        "BASE_CACHE_DIR": str(tmp_path / "cache"),
    }
    monkeypatch.setattr("bankbuddy.imports.extract_pdf_text", lambda _path: BOA_PDF_TEXT)

    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "12345678901145",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    import_result = runner.invoke(
        main,
        [
            "--debug",
            "--log-file",
            str(log_path),
            "import",
            "--file",
            str(pdf_path),
            "--account-id",
            "1",
        ],
        env=env,
    )

    assert add_result.exit_code == 0
    assert import_result.exit_code == 0
    assert "Rows imported: 2" in import_result.stdout
    assert "source_format=boa_pdf" in import_result.stderr
    log_text = log_path.read_text(encoding="utf-8")
    assert "rows_parsed=2 rows_imported=2 rows_skipped_duplicate=0" in log_text
    assert "account_suffix=1145" in log_text
    assert "12345678901145" not in log_text
    assert "12345678901145" not in import_result.stderr


def test_import_file_command_rejects_unsupported_file_type(tmp_path) -> None:
    statement_path = tmp_path / "statement.txt"
    statement_path.write_text("not supported", encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}

    result = runner.invoke(
        main,
        ["import", "--file", str(statement_path), "--account-id", "1"],
        env=env,
    )

    assert result.exit_code != 0
    assert "Unsupported import file type" in result.output
