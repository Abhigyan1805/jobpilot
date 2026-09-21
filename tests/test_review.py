import json
import tempfile
import unittest
from pathlib import Path

from jobpilot.review import build_packet
from tests.helpers import plan_for, posting


class ReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_distinct_postings_get_distinct_packet_dirs(self):
        title = "Software Development Engineer Internship - Summer 2026"
        first = posting(job_id="1234567", company="Amazon", title=title)
        second = posting(job_id="7654321", company="Amazon", title=title)

        first_dir = build_packet(plan_for(first), self.tmp.name)
        second_dir = build_packet(plan_for(second), self.tmp.name)

        self.assertNotEqual(first_dir, second_dir)
        packet = json.loads((Path(second_dir) / "packet.json").read_text(encoding="utf-8"))
        self.assertEqual(packet["stable_id"], second.stable_id)
        link = (Path(second_dir) / "apply_link.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(link, second.apply_url)


if __name__ == "__main__":
    unittest.main()
