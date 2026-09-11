import tempfile
import unittest
from pathlib import Path

from app import Store


class WorkerStoreTests(unittest.TestCase):
    def make_store(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Store(Path(temp.name) / "test.db")

    def test_only_one_job_can_be_running(self):
        store = self.make_store()
        first = store.enqueue("BOOK", 1, 1, "First")
        second = store.enqueue("BOOK", 1, 2, "Second")

        claimed = store.next_queued()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], first)

        # A second claimant must not start another job while one is running.
        self.assertIsNone(store.next_queued())

        store.update_job(first, "done")
        claimed = store.next_queued()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], second)

    def test_recover_stale_running_requeues_jobs(self):
        store = self.make_store()
        job_id = store.enqueue("BOOK", 1, 1, "Interrupted")
        claimed = store.next_queued()
        self.assertEqual(claimed["id"], job_id)

        recovered = store.recover_stale_running()
        self.assertEqual(recovered, 1)

        jobs = store.jobs()
        recovered_job = next(job for job in jobs if job["id"] == job_id)
        self.assertEqual(recovered_job["status"], "queued")
        self.assertIn("Recovered after service restart", recovered_job["error"])

    def test_worker_state_is_persisted_in_database(self):
        store = self.make_store()
        self.assertTrue(store.worker_enabled())
        store.set_worker_enabled(False)
        self.assertFalse(store.worker_enabled())
        store.set_worker_enabled(True)
        self.assertTrue(store.worker_enabled())


if __name__ == "__main__":
    unittest.main()
