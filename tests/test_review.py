import json
import tempfile
import unittest
from pathlib import Path

from jobpilot.models import GeneratedCoverLetter, GeneratedResume
from jobpilot.review import build_packet
from tests.helpers import plan_for, posting, strong_match


class ReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_packet_carries_resume_cover_link_and_jd_requirements(self):
        p = posting(job_id="packet-1", apply_url="https://example.com/packet-1/apply")
        match = strong_match(score=0.8, matched=("Python", "RAG"), missing=("Kubernetes",))
        plan = plan_for(p, match)
        resume_pdf = Path(self.tmp.name) / "resume.pdf"
        cover_pdf = Path(self.tmp.name) / "cover.pdf"
        resume_pdf.write_bytes(b"%PDF-1.4 resume")
        cover_pdf.write_bytes(b"%PDF-1.4 cover")
        plan.resume = GeneratedResume(pdf_path=str(resume_pdf))
        plan.cover = GeneratedCoverLetter(pdf_path=str(cover_pdf))

        packet_dir = Path(build_packet(plan, self.tmp.name))

        self.assertTrue((packet_dir / "resume.pdf").exists())
        self.assertTrue((packet_dir / "cover_letter.pdf").exists())
        self.assertEqual(
            (packet_dir / "apply_link.txt").read_text(encoding="utf-8").strip(),
            "https://example.com/packet-1/apply",
        )
        packet = json.loads((packet_dir / "packet.json").read_text(encoding="utf-8"))
        self.assertEqual(packet["matched_keywords"], ["Python", "RAG"])
        self.assertEqual(packet["gap_keywords"], ["Kubernetes"])
        requirements = (packet_dir / "requirements.md").read_text(encoding="utf-8")
        self.assertIn("Python", requirements)
        self.assertIn("Kubernetes", requirements)

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
