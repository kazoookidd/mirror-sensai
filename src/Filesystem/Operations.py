import os
from typing import Callable

from Filesystem.Permissions import (
    OP_LIST,
    OP_READ,
    OP_WRITE,
    PermissionDenied,
    PermissionPolicy,
    log_access,
)

DEFAULT_MAX_READ_BYTES = 1_000_000

ConfirmCallback = Callable[[str, str, str], bool]


class FileOperationError(Exception):
    pass


def cli_confirm(operation: str, path: str, detail: str) -> bool:
    print(f"\n[Permission] The agent wants to {operation}: {path}")
    if detail:
        print(f"             {detail}")
    try:
        answer = input("Allow? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes", "o", "oui")


class FileSystem:
    def __init__(
        self,
        policy: PermissionPolicy,
        confirm: ConfirmCallback | None = None,
        user_id: str | None = None,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
    ):
        self.policy = policy
        self.confirm = confirm
        self.user_id = user_id
        self.max_read_bytes = max_read_bytes

    def _authorize(self, raw_path: str, operation: str, detail: str = "") -> str:
        try:
            target = self.policy.check(raw_path, operation)
        except PermissionDenied as e:
            log_access(self.user_id, operation, str(raw_path), False, str(e))
            raise

        if self.policy.needs_confirmation(operation):
            approved = self.confirm(operation, str(target), detail) if self.confirm else False
            if not approved:
                reason = (
                    "write not validated by the user"
                    if self.confirm
                    else "write requires validation but no confirmation handler is configured"
                )
                log_access(self.user_id, operation, str(raw_path), False, reason)
                raise PermissionDenied(f"{operation} on '{raw_path}' refused: {reason}")

        log_access(self.user_id, operation, str(raw_path), True)
        return str(target)

    def read_file(self, path: str) -> str:
        target = self._authorize(path, OP_READ)

        if not os.path.isfile(target):
            raise FileOperationError(f"'{path}' is not an existing file.")
        size = os.path.getsize(target)
        if size > self.max_read_bytes:
            raise FileOperationError(
                f"'{path}' is too large to read ({size} bytes, limit {self.max_read_bytes})."
            )
        try:
            with open(target, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            raise FileOperationError(f"'{path}' is not a UTF-8 text file.")
        except OSError as e:
            raise FileOperationError(f"cannot read '{path}': {e.strerror}")

    def list_dir(self, path: str) -> list[str]:
        target = self._authorize(path, OP_LIST)

        if not os.path.isdir(target):
            raise FileOperationError(f"'{path}' is not an existing directory.")
        try:
            entries = sorted(os.listdir(target))
        except OSError as e:
            raise FileOperationError(f"cannot list '{path}': {e.strerror}")
        return [e + "/" if os.path.isdir(os.path.join(target, e)) else e for e in entries]

    def write_file(self, path: str, content: str) -> None:
        target = self._authorize(path, OP_WRITE, f"{len(content)} characters")

        if os.path.isdir(target):
            raise FileOperationError(f"'{path}' is a directory.")
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            raise FileOperationError(f"cannot write '{path}': {e.strerror}")
