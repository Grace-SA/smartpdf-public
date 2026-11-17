import unittest

from benchmark_process import parse_reply


class BenchmarkProcessTests(unittest.TestCase):
    def test_final_success_object_after_model_progress_is_preserved(self):
        reply = parse_reply(0, b'Loading model\n{"pages":1,"tables":2}\n')
        self.assertEqual(
            reply, {"status": "converted", "result": {"pages": 1, "tables": 2}}
        )

    def test_expected_refusal_requires_the_declared_exit_and_error_message(self):
        self.assertEqual(
            parse_reply(2, b'{"error":"Unlock this PDF before converting it."}'),
            {"status": "refused", "reason": "Unlock this PDF before converting it."},
        )
        for payload in [
            b'{"pages":1}',
            b'{"error":null}',
            b'{"error":false}',
            b'{"error":""}',
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(parse_reply(2, payload)["status"], "error")

    def test_success_json_followed_by_process_failure_is_never_counted_as_success_or_refusal(
        self,
    ):
        for code in [-11, -9, 1, 3]:
            with self.subTest(code=code):
                reply = parse_reply(code, b'{"pages":1,"tables":1}')
                self.assertEqual(reply["status"], "error")
                self.assertIn(str(code), reply["reason"])

    def test_malformed_or_empty_output_is_a_protocol_error(self):
        for payload in [b"", b"\n", b"not json", b"[]", b"null", b"\xff"]:
            with self.subTest(payload=payload):
                self.assertEqual(parse_reply(0, payload)["status"], "error")

    def test_error_payload_cannot_be_accepted_with_zero_exit(self):
        self.assertEqual(parse_reply(0, b'{"error":"failed"}')["status"], "error")
