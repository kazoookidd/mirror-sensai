import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from Filesystem.Permissions import DEFAULT_AUDIT_LOG_PATH
from Filesystem.Tools import build_filesystem, execute_tool

OUTPUT_FILE = "sorties_rh/demo_resume.txt"


def show(title: str, result: str) -> None:
    preview = result if len(result) <= 90 else result[:87].replace("\n", " ") + "..."
    print(f"{title}\n    -> {preview.replace(chr(10), ' | ')}\n")


def main() -> None:
    log_start = DEFAULT_AUDIT_LOG_PATH.stat().st_size if DEFAULT_AUDIT_LOG_PATH.exists() else 0

    answers = iter([True, False])

    def scripted_confirm(operation: str, path: str, detail: str) -> bool:
        approved = next(answers)
        print(f"    [confirmation] {operation} {path} ({detail}) -> {'oui' if approved else 'non'}")
        return approved

    fs = build_filesystem(confirm=scripted_confirm, user_id="demo")

    print("=== Lectures ===\n")
    show("read_file documents_rh/politique_conges.txt",
         execute_tool(fs, "read_file", {"path": "documents_rh/politique_conges.txt"}))
    show("list_dir documents_rh",
         execute_tool(fs, "list_dir", {"path": "documents_rh"}))
    show("read_file documents_rh/confidentiel/salaires.txt",
         execute_tool(fs, "read_file", {"path": "documents_rh/confidentiel/salaires.txt"}))
    show("read_file secrets/passwords.txt",
         execute_tool(fs, "read_file", {"path": "secrets/passwords.txt"}))
    show("read_file documents_rh/../secrets/passwords.txt",
         execute_tool(fs, "read_file", {"path": "documents_rh/../secrets/passwords.txt"}))
    show("read_file /etc/passwd",
         execute_tool(fs, "read_file", {"path": "/etc/passwd"}))

    print("=== Ecritures ===\n")
    show("write_file documents_rh/politique_conges.txt (lecture seule)",
         execute_tool(fs, "write_file", {"path": "documents_rh/politique_conges.txt", "content": "x"}))
    show(f"write_file {OUTPUT_FILE} (confirmation acceptee)",
         execute_tool(fs, "write_file", {"path": OUTPUT_FILE, "content": "Resume de la politique de conges."}))
    show("write_file sorties_rh/refuse.txt (confirmation refusee)",
         execute_tool(fs, "write_file", {"path": "sorties_rh/refuse.txt", "content": "x"}))

    written = ROOT / OUTPUT_FILE
    if written.exists():
        written.unlink()

    print("=== Nouvelles lignes de logs/access.log ===\n")
    with open(DEFAULT_AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        f.seek(log_start)
        print(f.read())


if __name__ == "__main__":
    main()
