import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Filesystem.Operations import FileOperationError, FileSystem
from Filesystem.Permissions import (
    PermissionDenied,
    PermissionPolicy,
    audit_logger,
    setup_audit_log,
)
from Filesystem.Tools import TOOL_DEFINITIONS, execute_tool

RH_RULES = [
    {"path": "documents_rh", "access": "read"},
    {"path": "documents_rh/confidentiel", "access": "none"},
    {"path": "sorties_rh", "access": "write"},
]


class FilesystemTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()

        (self.root / "documents_rh" / "confidentiel").mkdir(parents=True)
        (self.root / "documents_rh" / "politique_conges.txt").write_text("30 jours", encoding="utf-8")
        (self.root / "documents_rh" / "confidentiel" / "salaires.txt").write_text("52000", encoding="utf-8")
        (self.root / "documents_rh_evil").mkdir()
        (self.root / "documents_rh_evil" / "x.txt").write_text("evil", encoding="utf-8")
        (self.root / "sorties_rh").mkdir()
        (self.root / "secrets").mkdir()
        (self.root / "secrets" / "passwords.txt").write_text("hunter2", encoding="utf-8")

        self.log_path = self.root / "logs" / "access.log"
        self.log_handler_path = setup_audit_log(self.log_path)
        self.addCleanup(self._remove_log_handler)

    def _remove_log_handler(self):
        for h in list(audit_logger.handlers):
            if getattr(h, "baseFilename", None) == str(self.log_handler_path):
                h.close()
                audit_logger.removeHandler(h)

    def make_fs(self, rules=None, confirm=None, confirm_writes=True):
        rules = RH_RULES if rules is None else rules
        policy = PermissionPolicy(rules, base_dir=self.root, confirm_writes=confirm_writes)
        return FileSystem(policy, confirm=confirm, user_id="tester")

    def log_text(self):
        for h in audit_logger.handlers:
            h.flush()
        return self.log_path.read_text(encoding="utf-8") if self.log_path.exists() else ""


class TestReadPermissions(FilesystemTestCase):
    def test_allowed_file_is_readable(self):
        self.assertEqual(self.make_fs().read_file("documents_rh/politique_conges.txt"), "30 jours")

    def test_allowed_directory_is_listable(self):
        entries = self.make_fs().list_dir("documents_rh")
        self.assertIn("politique_conges.txt", entries)
        self.assertIn("confidentiel/", entries)

    def test_absolute_path_inside_scope_is_allowed(self):
        path = str(self.root / "documents_rh" / "politique_conges.txt")
        self.assertEqual(self.make_fs().read_file(path), "30 jours")

    def test_confidential_subdirectory_is_blocked_and_logged(self):
        fs = self.make_fs()
        with self.assertRaises(PermissionDenied):
            fs.read_file("documents_rh/confidentiel/salaires.txt")
        with self.assertRaises(PermissionDenied):
            fs.list_dir("documents_rh/confidentiel")
        log = self.log_text()
        self.assertIn("DENIED", log)
        self.assertIn("documents_rh/confidentiel/salaires.txt", log)

    def test_read_outside_scope_is_blocked_and_logged(self):
        fs = self.make_fs()
        with self.assertRaises(PermissionDenied):
            fs.read_file("secrets/passwords.txt")
        log = self.log_text()
        self.assertIn("DENIED", log)
        self.assertIn("op=read", log)
        self.assertIn("secrets/passwords.txt", log)
        self.assertIn("user=tester", log)

    def test_denied_attempt_does_not_leak_content(self):
        try:
            self.make_fs().read_file("secrets/passwords.txt")
        except PermissionDenied as e:
            self.assertNotIn("hunter2", str(e))

    def test_path_traversal_is_blocked(self):
        fs = self.make_fs()
        with self.assertRaises(PermissionDenied):
            fs.read_file("documents_rh/../secrets/passwords.txt")
        with self.assertRaises(PermissionDenied):
            fs.read_file("documents_rh/../../etc/passwd")
        with self.assertRaises(PermissionDenied):
            fs.read_file("documents_rh/politique_conges.txt/../confidentiel/salaires.txt")

    def test_sibling_directory_with_same_prefix_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            self.make_fs().read_file("documents_rh_evil/x.txt")

    def test_symlink_escaping_scope_is_blocked(self):
        link = self.root / "documents_rh" / "link.txt"
        try:
            link.symlink_to(self.root / "secrets" / "passwords.txt")
        except OSError:
            self.skipTest("symlinks not supported")
        with self.assertRaises(PermissionDenied):
            self.make_fs().read_file("documents_rh/link.txt")

    def test_null_byte_path_is_blocked(self):
        with self.assertRaises(PermissionDenied):
            self.make_fs().read_file("documents_rh/politique_conges.txt\x00../secrets/passwords.txt")
        self.assertIn("DENIED", self.log_text())

    def test_default_deny_with_empty_whitelist(self):
        with self.assertRaises(PermissionDenied):
            self.make_fs(rules=[]).read_file("documents_rh/politique_conges.txt")

    def test_allowed_access_is_logged_as_info(self):
        self.make_fs().read_file("documents_rh/politique_conges.txt")
        self.assertIn("ALLOWED", self.log_text())

    def test_missing_file_inside_scope(self):
        with self.assertRaises(FileOperationError):
            self.make_fs().read_file("documents_rh/nope.txt")

    def test_binary_file_is_rejected(self):
        (self.root / "documents_rh" / "bin.dat").write_bytes(b"\xff\xfe\x00\x80")
        with self.assertRaises(FileOperationError):
            self.make_fs().read_file("documents_rh/bin.dat")

    def test_oversized_file_is_rejected(self):
        fs = self.make_fs()
        fs.max_read_bytes = 3
        with self.assertRaises(FileOperationError):
            fs.read_file("documents_rh/politique_conges.txt")


class TestWritePermissions(FilesystemTestCase):
    def test_write_in_read_only_directory_is_blocked_even_if_user_would_approve(self):
        fs = self.make_fs(confirm=lambda *a: True)
        with self.assertRaises(PermissionDenied):
            fs.write_file("documents_rh/politique_conges.txt", "hacked")
        with self.assertRaises(PermissionDenied):
            fs.write_file("documents_rh/new.txt", "x")
        self.assertEqual((self.root / "documents_rh" / "politique_conges.txt").read_text(), "30 jours")
        self.assertFalse((self.root / "documents_rh" / "new.txt").exists())
        self.assertIn("op=write", self.log_text())

    def test_write_in_sorties_rh_after_confirmation(self):
        calls = []
        fs = self.make_fs(confirm=lambda op, path, detail: calls.append((op, path)) or True)
        fs.write_file("sorties_rh/resume.txt", "contenu")
        self.assertEqual((self.root / "sorties_rh" / "resume.txt").read_text(), "contenu")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "write")

    def test_write_can_overwrite_and_create_subdirectories(self):
        fs = self.make_fs(confirm=lambda *a: True)
        fs.write_file("sorties_rh/a.txt", "1")
        fs.write_file("sorties_rh/a.txt", "2")
        fs.write_file("sorties_rh/sub/deep/b.txt", "3")
        self.assertEqual((self.root / "sorties_rh" / "a.txt").read_text(), "2")
        self.assertEqual((self.root / "sorties_rh" / "sub" / "deep" / "b.txt").read_text(), "3")

    def test_write_without_confirmation_handler_is_refused(self):
        fs = self.make_fs()
        with self.assertRaises(PermissionDenied):
            fs.write_file("sorties_rh/resume.txt", "x")
        self.assertFalse((self.root / "sorties_rh" / "resume.txt").exists())

    def test_write_declined_by_user_is_refused_and_logged(self):
        fs = self.make_fs(confirm=lambda *a: False)
        with self.assertRaises(PermissionDenied):
            fs.write_file("sorties_rh/resume.txt", "x")
        self.assertFalse((self.root / "sorties_rh" / "resume.txt").exists())
        self.assertIn("not validated", self.log_text())

    def test_confirmation_can_be_disabled_by_policy(self):
        fs = self.make_fs(confirm_writes=False)
        fs.write_file("sorties_rh/auto.txt", "ok")
        self.assertTrue((self.root / "sorties_rh" / "auto.txt").exists())

    def test_reads_do_not_need_confirmation(self):
        fs = self.make_fs(confirm=lambda *a: self.fail("confirm must not be called for reads"))
        fs.read_file("documents_rh/politique_conges.txt")

    def test_write_outside_scope_is_blocked(self):
        fs = self.make_fs(confirm=lambda *a: True)
        with self.assertRaises(PermissionDenied):
            fs.write_file("secrets/new.txt", "x")
        with self.assertRaises(PermissionDenied):
            fs.write_file("sorties_rh/../secrets/new.txt", "x")
        self.assertFalse((self.root / "secrets" / "new.txt").exists())

    def test_write_on_directory_fails(self):
        fs = self.make_fs(confirm=lambda *a: True)
        with self.assertRaises(FileOperationError):
            fs.write_file("sorties_rh", "x")


class TestRuleSpecificity(FilesystemTestCase):
    def test_most_specific_rule_wins(self):
        fs = self.make_fs(
            rules=[
                {"path": "documents_rh", "access": "read"},
                {"path": "documents_rh/confidentiel", "access": "write"},
            ],
            confirm=lambda *a: True,
        )
        fs.write_file("documents_rh/confidentiel/ok.txt", "edited")
        with self.assertRaises(PermissionDenied):
            fs.write_file("documents_rh/politique_conges.txt", "edited")

    def test_single_file_rule(self):
        fs = self.make_fs(rules=[{"path": "secrets/passwords.txt", "access": "read"}])
        self.assertEqual(fs.read_file("secrets/passwords.txt"), "hunter2")
        with self.assertRaises(PermissionDenied):
            fs.read_file("documents_rh/politique_conges.txt")


class TestPolicyConfig(FilesystemTestCase):
    def test_invalid_access_level_is_rejected(self):
        with self.assertRaises(ValueError):
            PermissionPolicy([{"path": "x", "access": "admin"}], base_dir=self.root)

    def test_load_from_file_anchors_paths_on_config_directory(self):
        cfg = self.root / "permissions.json"
        cfg.write_text(json.dumps({"rules": RH_RULES}))
        fs = FileSystem(PermissionPolicy.from_file(cfg))
        self.assertEqual(fs.read_file("documents_rh/politique_conges.txt"), "30 jours")
        with self.assertRaises(PermissionDenied):
            fs.read_file("secrets/passwords.txt")

    def test_missing_config_falls_back_to_rh_policy(self):
        policy = PermissionPolicy.from_file(self.root / "does_not_exist.json")
        self.assertTrue(policy.confirm_writes)
        self.assertEqual(
            sorted((r.path.name, r.access) for r in policy.rules),
            [("confidentiel", "none"), ("documents_rh", "read"), ("sorties_rh", "write")],
        )

    def test_invalid_json_is_reported(self):
        cfg = self.root / "bad.json"
        cfg.write_text("{not json")
        with self.assertRaises(ValueError):
            PermissionPolicy.from_file(cfg)

    def test_shipped_permissions_file_matches_rh_policy(self):
        shipped = Path(__file__).resolve().parents[2] / "permissions.json"
        data = json.loads(shipped.read_text(encoding="utf-8"))
        self.assertEqual(data["rules"], RH_RULES)
        self.assertTrue(data["confirm_writes"])


class TestToolDispatcher(FilesystemTestCase):
    def test_tool_definitions(self):
        names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
        self.assertEqual(names, {"read_file", "list_dir", "write_file"})

    def test_allowed_read_returns_content(self):
        result = execute_tool(self.make_fs(), "read_file", {"path": "documents_rh/politique_conges.txt"})
        self.assertEqual(result, "30 jours")

    def test_denied_read_returns_access_denied_and_logs(self):
        result = execute_tool(self.make_fs(), "read_file", {"path": "secrets/passwords.txt"})
        self.assertTrue(result.startswith("Access denied"))
        self.assertNotIn("hunter2", result)
        self.assertIn("DENIED", self.log_text())

    def test_traversal_through_tool_is_denied(self):
        result = execute_tool(self.make_fs(), "read_file", {"path": "documents_rh/../secrets/passwords.txt"})
        self.assertTrue(result.startswith("Access denied"))
        self.assertNotIn("hunter2", result)

    def test_list_dir_tool(self):
        result = execute_tool(self.make_fs(), "list_dir", {"path": "documents_rh"})
        self.assertIn("politique_conges.txt", result)

    def test_write_tool_in_read_only_directory_is_denied(self):
        fs = self.make_fs(confirm=lambda *a: True)
        result = execute_tool(fs, "write_file", {"path": "documents_rh/politique_conges.txt", "content": "x"})
        self.assertTrue(result.startswith("Access denied"))

    def test_write_tool_in_sorties_rh_needs_confirmation(self):
        refused = execute_tool(self.make_fs(confirm=lambda *a: False), "write_file",
                               {"path": "sorties_rh/a.txt", "content": "x"})
        self.assertTrue(refused.startswith("Access denied"))
        accepted = execute_tool(self.make_fs(confirm=lambda *a: True), "write_file",
                                {"path": "sorties_rh/a.txt", "content": "x"})
        self.assertTrue(accepted.startswith("OK"))

    def test_bad_arguments_and_unknown_tool(self):
        fs = self.make_fs()
        self.assertTrue(execute_tool(fs, "read_file", {}).startswith("Error"))
        self.assertTrue(execute_tool(fs, "read_file", "oops").startswith("Error"))
        self.assertTrue(execute_tool(fs, "write_file", {"path": "sorties_rh/a.txt"}).startswith("Error"))
        self.assertTrue(execute_tool(fs, "rm_rf", {"path": "x"}).startswith("Error: unknown tool"))


if __name__ == "__main__":
    unittest.main()
