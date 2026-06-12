import tomllib


def test_project_installs_only_bankbuddy_console_command() -> None:
    with open("pyproject.toml", "rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    scripts = pyproject["project"]["scripts"]

    assert scripts == {"bankbuddy": "bankbuddy.cli:main"}
    assert "bank-buddy" not in scripts
