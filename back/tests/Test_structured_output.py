import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from Memories.Database import get_connection, init_db
from StructuredOutput.Extractor import (
    LEAVE_REQUEST_SCHEMA,
    StructuredOutputError,
    extract_leave_request,
)
from StructuredOutput.Schema import validate
from StructuredOutput.Store import list_leave_requests, save_leave_request

URL = "http://localhost:11434"
VALID = {
    "leave_type": "paid_leave",
    "start_date": "2026-11-03",
    "end_date": "2026-11-07",
    "reason": "vacances",
}


def _reply(content) -> mock.Mock:
    """A fake successful Ollama /api/chat response."""
    if not isinstance(content, str):
        content = json.dumps(content)
    response = mock.Mock()
    response.json.return_value = {"message": {"content": content}}
    response.raise_for_status.return_value = None
    return response


def _extract(text="je pose une semaine", **kwargs):
    return extract_leave_request(text, URL, "test-model", today=date(2026, 10, 14), **kwargs)


class SchemaValidationTests(unittest.TestCase):
    def test_valid_request_has_no_errors(self):
        self.assertEqual(validate(VALID, LEAVE_REQUEST_SCHEMA), [])

    def test_missing_required_field(self):
        data = {k: v for k, v in VALID.items() if k != "start_date"}
        errors = validate(data, LEAVE_REQUEST_SCHEMA)
        self.assertEqual(len(errors), 1)
        self.assertIn("start_date", errors[0])

    def test_wrong_type(self):
        errors = validate({**VALID, "reason": 42}, LEAVE_REQUEST_SCHEMA)
        self.assertIn("expected string", errors[0])

    def test_value_outside_enum(self):
        errors = validate({**VALID, "leave_type": "holiday"}, LEAVE_REQUEST_SCHEMA)
        self.assertIn("leave_type", errors[0])

    def test_unexpected_field_rejected(self):
        errors = validate({**VALID, "salary": 1}, LEAVE_REQUEST_SCHEMA)
        self.assertIn("unexpected field 'salary'", errors[0])

    def test_invalid_dates_rejected(self):
        for bad in ("2026-13-01", "2026-02-30", "03/11/2026", "20261103", "demain"):
            with self.subTest(date=bad):
                errors = validate({**VALID, "start_date": bad}, LEAVE_REQUEST_SCHEMA)
                self.assertTrue(errors)

    def test_boolean_is_not_a_number(self):
        self.assertTrue(validate(True, {"type": "integer"}))
        self.assertEqual(validate(3, {"type": "integer", "minimum": 1}), [])
        self.assertTrue(validate(0, {"type": "integer", "minimum": 1}))

    def test_nested_array_errors_have_a_path(self):
        schema = {"type": "array", "items": {"type": "string"}}
        errors = validate(["a", 2], schema)
        self.assertTrue(errors[0].startswith("$[1]"))

    def test_non_object_root(self):
        self.assertTrue(validate([], LEAVE_REQUEST_SCHEMA))


class ExtractionTests(unittest.TestCase):
    def test_valid_answer_returned_on_first_attempt(self):
        with mock.patch("requests.post", return_value=_reply(VALID)) as post:
            self.assertEqual(_extract(), VALID)
        self.assertEqual(post.call_count, 1)

    def test_schema_is_sent_to_ollama(self):
        with mock.patch("requests.post", return_value=_reply(VALID)) as post:
            _extract()
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["format"], LEAVE_REQUEST_SCHEMA)
        self.assertFalse(body["stream"])
        self.assertEqual(body["options"]["temperature"], 0)

    def test_today_is_given_to_the_model(self):
        with mock.patch("requests.post", return_value=_reply(VALID)) as post:
            _extract()
        system = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("2026-10-14", system)

    def test_retry_after_invalid_json(self):
        replies = [_reply("Sure! Here you go: {oops"), _reply(VALID)]
        with mock.patch("requests.post", side_effect=replies) as post:
            self.assertEqual(_extract(), VALID)
        self.assertEqual(post.call_count, 2)

    def test_retry_feeds_the_errors_back_to_the_model(self):
        bad = {**VALID, "leave_type": "holiday"}
        with mock.patch("requests.post", side_effect=[_reply(bad), _reply(VALID)]) as post:
            _extract()
        second_call = post.call_args_list[1].kwargs["json"]["messages"]
        self.assertEqual(second_call[-2], {"role": "assistant", "content": json.dumps(bad)})
        self.assertIn("leave_type", second_call[-1]["content"])

    def test_end_before_start_is_rejected_then_corrected(self):
        backwards = {**VALID, "start_date": "2026-11-07", "end_date": "2026-11-03"}
        with mock.patch("requests.post", side_effect=[_reply(backwards), _reply(VALID)]) as post:
            self.assertEqual(_extract(), VALID)
        self.assertEqual(post.call_count, 2)

    def test_gives_up_after_max_attempts(self):
        bad = {**VALID, "leave_type": "holiday"}
        with mock.patch("requests.post", return_value=_reply(bad)) as post:
            with self.assertRaises(StructuredOutputError) as ctx:
                _extract(max_attempts=2)
        self.assertEqual(post.call_count, 2)
        self.assertIn("no valid answer after 2 attempts", str(ctx.exception))

    def test_empty_input_never_calls_the_model(self):
        with mock.patch("requests.post") as post:
            with self.assertRaises(StructuredOutputError):
                _extract("   ")
        post.assert_not_called()

    def test_connection_error_is_not_retried(self):
        with mock.patch("requests.post", side_effect=requests.exceptions.ConnectionError) as post:
            with self.assertRaises(StructuredOutputError) as ctx:
                _extract()
        self.assertEqual(post.call_count, 1)
        self.assertIn("Ollama", str(ctx.exception))

    def test_http_error_becomes_clean_error(self):
        response = mock.Mock()
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        with mock.patch("requests.post", return_value=response):
            with self.assertRaises(StructuredOutputError):
                _extract()

    def test_malformed_ollama_response(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"unexpected": True}
        with mock.patch("requests.post", return_value=response):
            with self.assertRaises(StructuredOutputError):
                _extract()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._dir.name, "test.db")
        init_db(self.db)
        conn = get_connection(self.db)
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, salt) "
            "VALUES ('alice', 'a@x.fr', 'h', 's')")
        conn.commit()
        conn.close()

    def tearDown(self):
        self._dir.cleanup()

    def test_save_and_list(self):
        request_id = save_leave_request("alice", VALID, self.db)
        rows = list_leave_requests("alice", self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], request_id)
        for key, value in VALID.items():
            self.assertEqual(rows[0][key], value)

    def test_most_recent_first_and_isolated_per_user(self):
        save_leave_request("alice", VALID, self.db)
        second = save_leave_request("alice", {**VALID, "reason": "autre"}, self.db)
        self.assertEqual(list_leave_requests("alice", self.db)[0]["id"], second)
        self.assertEqual(list_leave_requests("bob", self.db), [])

    def test_unknown_user_rejected(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            save_leave_request("ghost", VALID, self.db)


if __name__ == "__main__":
    unittest.main()
