import unittest

from job_alert.matching import extract_years, match_job
from job_alert.models import Job


CONFIG = {
    "title_keywords": ["software engineer ii", "backend engineer"],
    "include_keywords": ["backend", "distributed systems"],
    "exclude_title_keywords": ["intern", "staff"],
    "exclude_keywords": [],
    "skills": ["python", "java"],
    "locations": ["bangalore", "remote"],
    "min_years": 1,
    "max_years": 5,
    "minimum_score": 4,
    "require_title_keyword": True,
    "allow_unknown_location": True,
}


class MatchingTests(unittest.TestCase):
    def make_job(self, **changes):
        values = dict(source="test", external_id="1", title="Software Engineer II, Backend",
                      company="Acme", location="Bangalore", url="https://example.test/1",
                      description="Build distributed systems with Python. 2-4 years experience.")
        values.update(changes)
        return Job(**values)

    def test_matching_job(self):
        result = match_job(self.make_job(), CONFIG)
        self.assertTrue(result.matched)
        self.assertGreaterEqual(result.score, 4)

    def test_excluded_job(self):
        result = match_job(self.make_job(title="Software Engineering Intern"), CONFIG)
        self.assertFalse(result.matched)
        self.assertIn("excluded", result.reasons[0])

    def test_non_internship_qualification_does_not_exclude_engineer(self):
        job = self.make_job(description="Backend Python APIs. 3+ years of non-internship experience.")
        self.assertTrue(match_job(job, CONFIG).matched)

    def test_experience_outside_range(self):
        result = match_job(self.make_job(description="Backend Python role requiring 8+ years."), CONFIG)
        self.assertFalse(result.matched)

    def test_extract_year_range(self):
        self.assertEqual(extract_years("Requires 2-4 years of work"), (2, 4))


if __name__ == "__main__":
    unittest.main()
