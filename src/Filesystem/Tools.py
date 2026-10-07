import os

from Filesystem.Operations import (
    ConfirmCallback,
    FileOperationError,
    FileSystem,
)
from Filesystem.Permissions import (
    PermissionDenied,
    PermissionPolicy,
    setup_audit_log,
)


def build_filesystem(
    confirm: ConfirmCallback | None = None,
    user_id: str | None = None,
) -> FileSystem:
    setup_audit_log(os.getenv("FS_AUDIT_LOG_PATH") or None)
    policy = PermissionPolicy.from_file(os.getenv("FS_PERMISSIONS_PATH") or None)
    return FileSystem(policy, confirm=confirm, user_id=user_id)


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_PATH = {"type": "string", "description": "File or directory path, e.g. documents_rh/politique_conges.txt"}
_CONTENT = {"type": "string", "description": "Full text content to write in the file."}

TOOL_DEFINITIONS = [
    _tool(
        "read_file",
        "Read a text file. Only works inside the authorised directories.",
        {"path": _PATH},
        ["path"],
    ),
    _tool(
        "list_dir",
        "List the entries of a directory inside the authorised directories.",
        {"path": _PATH},
        ["path"],
    ),
    _tool(
        "write_file",
        "Create or overwrite a text file. Only allowed in writable directories and requires user confirmation.",
        {"path": _PATH, "content": _CONTENT},
        ["path", "content"],
    ),
]


def execute_tool(fs: FileSystem, name: str, arguments: dict) -> str:
    if not isinstance(arguments, dict):
        return "Error: tool arguments must be an object."

    path = arguments.get("path")
    if not isinstance(path, str) or not path:
        return "Error: missing required argument 'path'."

    try:
        if name == "read_file":
            return fs.read_file(path)
        if name == "list_dir":
            return "\n".join(fs.list_dir(path)) or "(empty directory)"
        if name == "write_file":
            content = arguments.get("content")
            if not isinstance(content, str):
                return "Error: missing required argument 'content'."
            fs.write_file(path, content)
            return f"OK: '{path}' written."
    except PermissionDenied as e:
        return f"Access denied: {e}"
    except FileOperationError as e:
        return f"Error: {e}"

    return f"Error: unknown tool '{name}'."
