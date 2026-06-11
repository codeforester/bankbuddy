from click.testing import CliRunner

from bankbuddy.cli import main


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
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
