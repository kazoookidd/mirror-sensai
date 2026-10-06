import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "permissions.json"
DEFAULT_AUDIT_LOG_PATH = PROJECT_ROOT / "logs" / "access.log"

OP_READ = "read"
OP_LIST = "list"
OP_WRITE = "write"

WRITE_OPERATIONS = {OP_WRITE}

ACCESS_NONE = "none"
ACCESS_READ = "read"
ACCESS_WRITE = "write"

_ALLOWED_OPERATIONS = {
    ACCESS_NONE: set(),
    ACCESS_READ: {OP_READ, OP_LIST},
    ACCESS_WRITE: {OP_READ, OP_LIST, OP_WRITE},
}

DEFAULT_RULES = [
    {"path": "documents_rh", "access": ACCESS_READ},
    {"path": "documents_rh/confidentiel", "access": ACCESS_NONE},
    {"path": "sorties_rh", "access": ACCESS_WRITE},
]

audit_logger = logging.getLogger("sensai.filesystem")
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False


class PermissionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Rule:
    path: Path
    access: str

    def contains(self, target: Path) -> bool:
        return target == self.path or self.path in target.parents


def setup_audit_log(log_path: str | os.PathLike | None = None) -> Path:
    path = Path(log_path) if log_path else DEFAULT_AUDIT_LOG_PATH
    path = path.expanduser().resolve()

    for handler in audit_logger.handlers:
        if getattr(handler, "baseFilename", None) == str(path):
            return path

    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    audit_logger.addHandler(handler)
    return path


class PermissionPolicy:
    def __init__(
        self,
        rules: list[dict],
        base_dir: str | os.PathLike = PROJECT_ROOT,
        confirm_writes: bool = True,
    ):
        self.base_dir = Path(os.path.realpath(base_dir))
        self.confirm_writes = confirm_writes
        self.rules: list[Rule] = []

        for raw in rules:
            access = raw.get("access")
            if access not in _ALLOWED_OPERATIONS:
                raise ValueError(
                    f"Invalid access level {access!r} for {raw.get('path')!r} "
                    f"(expected one of {sorted(_ALLOWED_OPERATIONS)})."
                )
            if not raw.get("path"):
                raise ValueError("Each permission rule needs a 'path'.")
            self.rules.append(Rule(self.resolve(raw["path"]), access))

    @classmethod
    def from_file(cls, config_path: str | os.PathLike | None = None) -> "PermissionPolicy":
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        if not path.is_file():
            return cls(DEFAULT_RULES)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid permissions file {path}: {e}") from e

        base_dir = path.parent / data.get("base_dir", ".")
        return cls(
            data.get("rules", []),
            base_dir=base_dir,
            confirm_writes=data.get("confirm_writes", True),
        )

    def resolve(self, raw_path: str | os.PathLike) -> Path:
        raw = os.fspath(raw_path)
        if "\x00" in raw:
            raise PermissionDenied("invalid path (null byte)")
        return Path(os.path.realpath(os.path.join(self.base_dir, os.path.expanduser(raw))))

    def _matching_rule(self, target: Path) -> Rule | None:
        matches = [r for r in self.rules if r.contains(target)]
        return max(matches, key=lambda r: len(r.path.parts), default=None)

    def check(self, raw_path: str | os.PathLike, operation: str) -> Path:
        target = self.resolve(raw_path)
        rule = self._matching_rule(target)

        if rule is None:
            raise PermissionDenied(f"'{raw_path}' is outside the authorised directories")
        if operation not in _ALLOWED_OPERATIONS[rule.access]:
            raise PermissionDenied(
                f"'{operation}' not allowed on '{raw_path}' (access level: {rule.access})"
            )
        return target

    def needs_confirmation(self, operation: str) -> bool:
        return self.confirm_writes and operation in WRITE_OPERATIONS


def log_access(user_id: str | None, operation: str, path: str, allowed: bool, reason: str = "") -> None:
    who = user_id or "-"
    if allowed:
        audit_logger.info("ALLOWED user=%s op=%s path=%s", who, operation, path)
    else:
        audit_logger.warning("DENIED user=%s op=%s path=%s reason=%s", who, operation, path, reason)
