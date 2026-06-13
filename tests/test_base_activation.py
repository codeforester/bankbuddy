import os
import subprocess

import yaml


def test_base_manifest_sources_activation_script() -> None:
    with open("base_manifest.yaml", encoding="utf-8") as manifest_file:
        manifest = yaml.safe_load(manifest_file)

    assert manifest["activate"]["source"] == [".base/activate.sh"]


def test_activation_defaults_bankbuddy_environment_to_dev() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source .base/activate.sh; printf "%s\\n" "$BANKBUDDY_ENV"',
        ],
        check=True,
        env=minimal_env(),
        capture_output=True,
        text=True,
    )

    assert result.stdout == "dev\n"


def test_activation_preserves_existing_bankbuddy_environment() -> None:
    env = minimal_env()
    env["BANKBUDDY_ENV"] = "prod"

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source .base/activate.sh; printf "%s\\n" "$BANKBUDDY_ENV"',
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout == "prod\n"


def minimal_env() -> dict[str, str]:
    return {
        "HOME": os.environ["HOME"],
        "PATH": os.environ["PATH"],
    }
