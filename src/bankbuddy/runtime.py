"""Base-style CLI runtime support for BankBuddy."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import platform
import shutil
import sys
import time
from typing import Any, Callable
import uuid


CLI_NAME = "bankbuddy"


class RuntimeConfigError(ValueError):
    """Raised when CLI runtime configuration cannot be loaded."""


@dataclass
class CliRuntime:
    """Runtime context shared by BankBuddy CLI commands."""

    cli_name: str
    run_id: str
    state_dir: Path
    log_dir: Path
    cache_dir: Path
    temp_dir: Path
    log_file: Path | None
    config: dict[str, Any]
    environment: str
    debug: bool
    keep_temp: bool
    log: logging.Logger
    project_root: Path | None = None
    manifest_path: Path | None = None
    cleanup_hooks: list[Callable[[], None]] = field(default_factory=list)

    def on_cleanup(self, hook: Callable[[], None]) -> None:
        """Register a callback to run when the CLI command exits."""

        self.cleanup_hooks.append(hook)

    def cleanup(self) -> None:
        """Run cleanup hooks, remove temp files, and close log handlers."""

        for hook in self.cleanup_hooks:
            try:
                hook()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self.log.warning("Cleanup hook failed: %s", exc)

        if not self.keep_temp and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except OSError as exc:
                self.log.warning(
                    "Temp directory cleanup failed for '%s': %s",
                    self.temp_dir,
                    exc,
                )

        for handler in list(self.log.handlers):
            try:
                handler.flush()
            finally:
                handler.close()
                self.log.removeHandler(handler)


def create_runtime(
    *,
    debug: bool,
    environment: str | None,
    config_path: str | None,
    keep_temp: bool,
    log_file: str | None,
) -> CliRuntime:
    """Create a Base-style runtime context for a BankBuddy CLI invocation."""

    run_id = make_run_id()
    manifest_path = discover_manifest(Path.cwd())
    project_root = manifest_path.parent if manifest_path is not None else None
    explicit_config = Path(config_path).expanduser() if config_path else None
    config = load_config(project_root, explicit_config)

    resolved_environment = environment or config.get("environment") or "dev"
    resolved_debug = debug or str(config.get("log_level", "")).lower() == "debug"
    resolved_keep_temp = keep_temp or bool(config.get("keep_temp"))

    state_dir = base_cache_root() / "cli" / CLI_NAME
    log_dir = state_dir / "logs"
    cache_dir = state_dir / "cache"
    temp_dir = state_dir / "tmp" / run_id
    resolved_log_file = Path(log_file).expanduser() if log_file else log_dir / f"{run_id}.log"

    prepared_log_file = prepare_runtime_dirs(
        log_file=resolved_log_file,
        log_dir=log_dir,
        cache_dir=cache_dir,
        temp_dir=temp_dir,
        keep_temp=resolved_keep_temp,
        explicit_log_file=bool(log_file),
    )
    logger = configure_logger(CLI_NAME, prepared_log_file, resolved_debug)
    logger.debug(
        "cli=%s run_id=%s environment=%s",
        CLI_NAME,
        run_id,
        resolved_environment,
    )
    if project_root is not None:
        logger.debug("project_root=%s", project_root)
    if manifest_path is not None:
        logger.debug("manifest_path=%s", manifest_path)
    logger.debug("platform=%s %s", platform.system(), platform.machine())
    logger.debug("python=%s", sys.version.replace("\n", " "))

    return CliRuntime(
        cli_name=CLI_NAME,
        run_id=run_id,
        state_dir=state_dir,
        log_dir=log_dir,
        cache_dir=cache_dir,
        temp_dir=temp_dir,
        log_file=prepared_log_file,
        config=config,
        environment=resolved_environment,
        debug=resolved_debug,
        keep_temp=resolved_keep_temp,
        log=logger,
        project_root=project_root,
        manifest_path=manifest_path,
    )


def prepare_runtime_dirs(
    *,
    log_file: Path,
    log_dir: Path,
    cache_dir: Path,
    temp_dir: Path,
    keep_temp: bool,
    explicit_log_file: bool,
) -> Path | None:
    """Create runtime directories, falling back to stderr when unavailable."""

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        if keep_temp:
            temp_dir.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        if explicit_log_file:
            raise
        return None
    return log_file


def configure_logger(cli_name: str, log_file: Path | None, debug: bool) -> logging.Logger:
    """Configure a Base-style logger for stderr and optional file diagnostics."""

    logger = logging.getLogger(f"base_cli.{cli_name}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

    user_handler = logging.StreamHandler()
    user_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    user_handler.setFormatter(BaseCliFormatter())
    logger.addHandler(user_handler)

    if log_file is not None:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        log_file.chmod(0o600)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(BaseCliFormatter())
        logger.addHandler(file_handler)
    return logger


class BaseCliFormatter(logging.Formatter):
    """Formatter compatible with Base CLI diagnostics."""

    def __init__(self) -> None:
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        source = source_path(record)
        level = level_name(record)
        return f"{timestamp} {level:<7} {source}:{record.lineno} {record.getMessage()}"


def level_name(record: logging.LogRecord) -> str:
    """Return Base's short display name for a log level."""

    if record.levelno == logging.WARNING:
        return "WARN"
    if record.levelno == logging.CRITICAL:
        return "FATAL"
    return record.levelname


def source_path(record: logging.LogRecord) -> str:
    """Return a compact source path for a log record."""

    path = Path(record.pathname)
    candidates = [Path.cwd()]
    base_home = os.environ.get("BASE_HOME")
    if base_home:
        candidates.insert(0, Path(base_home))

    for root in candidates:
        try:
            return str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            continue
    return str(path.resolve())


def make_run_id() -> str:
    """Return a timestamped run id for runtime files."""

    timestamp = time.strftime("%Y%m%dT%H%M%S")
    return f"{timestamp}_{uuid.uuid4().hex[:8]}"


def base_cache_root(home: Path | None = None) -> Path:
    """Return Base's cache root for CLI runtime files."""

    value = os.environ.get("BASE_CACHE_DIR")
    if value:
        return Path(value).expanduser()
    root = home or Path.home()
    if sys.platform == "darwin":
        return root / "Library" / "Caches" / "base"
    return root / ".cache" / "base"


def discover_manifest(start: Path) -> Path | None:
    """Find the nearest Base manifest from the current working tree."""

    current = start.resolve()
    if current.is_file():
        current = current.parent

    while True:
        candidate = current / "base_manifest.yaml"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def user_config_path(home: Path | None = None) -> Path:
    """Return the Base user config path."""

    return (home or Path.home()) / ".base.d" / "config.yaml"


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Load an optional YAML mapping from disk."""

    if not path.is_file():
        return {}

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeConfigError("PyYAML is required to load CLI configuration.") from exc

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeConfigError(f"Config file '{path}' contains invalid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RuntimeConfigError(f"Config file '{path}' must contain a YAML mapping.")
    return data


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge two config dictionaries recursively."""

    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(
    project_root: Path | None,
    explicit_config: Path | None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Load Base-style config from user, project, explicit, and env sources."""

    root = home or Path.home()
    config: dict[str, Any] = {}
    config = merge_dicts(config, load_yaml_file(user_config_path(root)))
    if project_root is not None:
        config = merge_dicts(config, load_yaml_file(project_root / ".base" / "config.yaml"))
    if explicit_config is not None:
        config = merge_dicts(config, load_yaml_file(explicit_config))

    env_config: dict[str, Any] = {}
    if "BASE_CLI_ENVIRONMENT" in os.environ:
        env_config["environment"] = os.environ["BASE_CLI_ENVIRONMENT"]
    if "BASE_CLI_LOG_LEVEL" in os.environ:
        env_config["log_level"] = os.environ["BASE_CLI_LOG_LEVEL"]
    elif os.environ.get("LOG_DEBUG", "").lower() in ("1", "true"):
        env_config["log_level"] = "debug"
    if "BASE_CLI_KEEP_TEMP" in os.environ:
        env_config["keep_temp"] = os.environ["BASE_CLI_KEEP_TEMP"].lower() == "true"
    return merge_dicts(config, env_config)
