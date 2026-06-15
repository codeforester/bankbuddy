import tomllib


def test_project_installs_bankbuddy_and_taxbuddy_console_commands() -> None:
    with open("pyproject.toml", "rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    scripts = pyproject["project"]["scripts"]

    assert scripts == {
        "bankbuddy": "bankbuddy.cli:main",
        "taxbuddy": "bankbuddy.tax.cli:main",
    }
    assert "bank-buddy" not in scripts
