import unittest

from progress_detection import completion_signal, resource_complete, section_complete


class ProgressDetectionTests(unittest.TestCase):
    def test_boolean_completion_fields(self):
        self.assertTrue(resource_complete({"is_completed": True}))
        self.assertFalse(resource_complete({"is_completed": False}))

    def test_status_completion(self):
        self.assertTrue(resource_complete({"status": "completed"}))
        self.assertFalse(resource_complete({"status": "in_progress"}))

    def test_percent_completion(self):
        self.assertTrue(resource_complete({"completion_percentage": 100}))
        self.assertFalse(resource_complete({"completion_percentage": 80}))

    def test_completed_total_pair(self):
        self.assertTrue(resource_complete({"progress": {"completed": 4, "total": 4}}))
        self.assertFalse(resource_complete({"progress": {"completed": 3, "total": 4}}))

    def test_part_level_completion(self):
        self.assertTrue(resource_complete({"parts": [{"complete": True}, {"completed": True}]}))
        self.assertFalse(resource_complete({"parts": [{"complete": True}, {"completed": False}]}))

    def test_section_level_completion_wins(self):
        complete, reason = section_complete(
            {"student_progress": {"completion_percent": 100}},
            [{"complete": False}],
        )
        self.assertTrue(complete)
        self.assertIn("section-level", reason)

    def test_all_resources_complete(self):
        complete, reason = section_complete(
            {},
            [
                {"progress": {"completed": 2, "total": 2}},
                {"status": "done"},
            ],
        )
        self.assertTrue(complete)
        self.assertIn("all activity", reason)

    def test_ambiguous_payload_is_not_assumed_complete(self):
        self.assertIsNone(completion_signal({"id": 123, "title": "Activity"}))


if __name__ == "__main__":
    unittest.main()
