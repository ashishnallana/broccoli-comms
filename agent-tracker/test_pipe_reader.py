import argparse
import io
import unittest
from unittest import mock

import pipe_reader


class TestPipeReader(unittest.TestCase):
    def test_utf8_boundary_handling(self):
        chunks = list(pipe_reader.iter_utf8_chunks([b"hello ", b"\xe2", b"\x82\xac world"], max_chunk_bytes=100))
        self.assertEqual(chunks, ["hello € world"])

    def test_chunk_cap_preserves_sequence_chunks(self):
        chunks = list(pipe_reader.iter_utf8_chunks([b"abcdef"], max_chunk_bytes=3))
        self.assertEqual(chunks, ["abc", "def"])

    def test_run_reader_sequences_capped_chunks(self):
        args = argparse.Namespace(
            socket="sock",
            agent_id="id-1",
            tmux_pane="%1",
            pipe_instance_id="pipe-1",
            pipe_token="token",
            read_size=64,
            max_chunk_bytes=3,
            max_buffer_bytes=100,
            retries=1,
            backoff=0,
        )
        submitted = []
        with mock.patch.object(pipe_reader, "submit_pane_output", side_effect=lambda _socket, payload, retries, backoff: submitted.append(payload) or True):
            rc = pipe_reader.run_reader(args, io.BytesIO(b"abcdef"))
        self.assertEqual(rc, 0)
        self.assertEqual([p["seq"] for p in submitted], [1, 2])
        self.assertEqual([p["chunk"] for p in submitted], ["abc", "def"])

    def test_submit_retry_drop_does_not_log_raw_chunk_or_token(self):
        payload = {
            "agent_id": "id-1",
            "tmux_pane": "%1",
            "pipe_instance_id": "pipe-1",
            "pipe_token": "SECRET_TOKEN",
            "seq": 1,
            "chunk": "RAW_SECRET_CHUNK",
        }
        with mock.patch.object(pipe_reader, "call_rpc", side_effect=OSError("down")), \
             mock.patch.object(pipe_reader.time, "sleep"), \
             mock.patch.object(pipe_reader.logging, "warning") as warning:
            ok = pipe_reader.submit_pane_output("sock", payload, retries=2, backoff=0)
        self.assertFalse(ok)
        logged = str(warning.call_args_list)
        self.assertNotIn("RAW_SECRET_CHUNK", logged)
        self.assertNotIn("SECRET_TOKEN", logged)
        self.assertIn("chunk_bytes", logged)


if __name__ == "__main__":
    unittest.main()
