from click.testing import CliRunner

from bankbuddy.tax.cli import main


US_1099_INT_TEXT = """\
Form 1099-INT
Tax Year 2025
Payer: Bank of America
Account number ending in 1234
"""


def test_taxbuddy_help_includes_base_runtime_options() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "taxbuddy" in result.output
    for option in (
        "-v, --debug",
        "--environment",
        "--config",
        "--keep-temp",
        "--log-file",
    ):
        assert option in result.output


def test_taxbuddy_status_reports_environment_and_paths(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["status"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home"), "BANKBUDDY_ENV": "dev"},
    )

    assert result.exit_code == 0
    assert "Environment: dev" in result.output
    assert f"Data home: {tmp_path / 'home'}" in result.output
    assert f"Database: {tmp_path / 'home' / 'database' / 'bankbuddy.sqlite3'}" in (
        result.output
    )
    assert f"Tax inbox: {tmp_path / 'home' / 'tax' / 'inbox'}" in result.output
    assert "Initialized: no" in result.output


def test_taxbuddy_import_file_dry_run_reports_plan_without_writes(tmp_path) -> None:
    source_path = tmp_path / "boa-1099.txt"
    source_path.write_text(US_1099_INT_TEXT, encoding="utf-8")
    home = tmp_path / "home"

    result = CliRunner().invoke(
        main,
        ["import", "--dry-run", "--file", str(source_path)],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "File: boa-1099.txt" in result.output
    assert "Document type: 1099-INT" in result.output
    assert "Jurisdiction: US" in result.output
    assert "Tax year: 2025" in result.output
    assert "Source: Bank of America" in result.output
    assert (
        "Processed path: tax/processed/us/2025/1099-int/"
        "2025_1099-int_bank-of-america_1234.txt"
    ) in result.output
    assert "Database changed: no" in result.output
    assert "Files changed: none" in result.output
    assert not (home / "tax/processed").exists()


def test_taxbuddy_import_file_indexes_document(tmp_path) -> None:
    source_path = tmp_path / "boa-1099.txt"
    source_path.write_text(US_1099_INT_TEXT, encoding="utf-8")
    home = tmp_path / "home"
    runner = CliRunner()

    result = runner.invoke(
        main,
        ["import", "--file", str(source_path)],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "File: boa-1099.txt" in result.output
    assert "Document ID: 1" in result.output
    assert "Duplicate: no" in result.output
    assert (
        "Processed path: tax/processed/us/2025/1099-int/"
        "2025_1099-int_bank-of-america_1234.txt"
    ) in result.output
    assert (
        home
        / "tax/processed/us/2025/1099-int/"
        "2025_1099-int_bank-of-america_1234.txt"
    ).is_file()

    duplicate = runner.invoke(
        main,
        ["import", "--file", str(source_path)],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert duplicate.exit_code == 0
    assert "Document ID: 1" in duplicate.output
    assert "Duplicate: yes" in duplicate.output


def test_taxbuddy_docs_list_and_show(tmp_path) -> None:
    source_path = tmp_path / "boa-1099.txt"
    source_path.write_text(US_1099_INT_TEXT, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(main, ["import", "--file", str(source_path)], env=env)

    listed = runner.invoke(main, ["docs", "list", "--year", "2025"], env=env)
    shown = runner.invoke(main, ["docs", "show", "1"], env=env)

    assert listed.exit_code == 0
    assert "ID | Year | Type     | Jurisdiction | Source          | Account" in (
        listed.output
    )
    assert " 1 | 2025 | 1099-INT | US           | Bank of America | 1234" in (
        listed.output
    )
    assert shown.exit_code == 0
    assert "Document ID: 1" in shown.output
    assert "Canonical: 2025_1099-int_bank-of-america_1234.txt" in shown.output
    assert "Processed: tax/processed/us/2025/1099-int/" in shown.output


def test_taxbuddy_import_inbox_dry_run_reports_each_file(tmp_path) -> None:
    home = tmp_path / "home"
    inbox = home / "tax" / "inbox"
    inbox.mkdir(parents=True)
    inbox_file = inbox / "boa-1099.txt"
    inbox_file.write_text(US_1099_INT_TEXT, encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["import", "--dry-run", "inbox"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "Inbox files: 1" in result.output
    assert "Planned imports: 1" in result.output
    assert (
        "would-import  boa-1099.txt  type=1099-INT year=2025 "
        "canonical=tax/processed/us/2025/1099-int/"
        "2025_1099-int_bank-of-america_1234.txt"
    ) in result.output
    assert inbox_file.is_file()
