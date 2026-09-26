"""Store migration safety for columns the current schema no longer uses."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jobpilot.store import Store
from tests.helpers import posting


class LegacyColumnTests(unittest.TestCase):
    def test_db_with_a_leftover_applicants_column_still_opens_and_upserts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "jobpilot.db"
            store = Store(db)
            # An earlier revision had this column; the current one never reads or
            # writes it, but the leftover must not break opens or upserts.
            store.conn.execute("ALTER TABLE postings ADD COLUMN applicants INTEGER")
            store.conn.commit()
            store.close()

            store = Store(db)
            try:
                p = posting(job_id="legacy", title="Machine Learning Intern")
                store.upsert_posting(p, eligible=True)
                self.assertEqual(store.get_posting(p.stable_id)["title"], p.title)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
