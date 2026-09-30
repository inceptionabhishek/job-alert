import unittest
from urllib.parse import parse_qs, urlsplit

from job_alert.adapters.amazon import AmazonAdapter
from job_alert.adapters.generic_html import GenericHtmlAdapter
from job_alert.adapters.greenhouse import GreenhouseAdapter
from job_alert.adapters.lever import LeverAdapter


class FakeHttp:
    def __init__(self, payload=None, text=""):
        self.payload = payload
        self.text = text

    def get_json(self, url):
        return self.payload

    def get_text(self, url):
        return self.text


class AdapterTests(unittest.TestCase):
    def test_cred_lever_mapping_includes_qualification_sections(self):
        item = {
            "id": "cred-job-1", "text": "Backend Engineer", "categories": {"location": "bengaluru"},
            "hostedUrl": "https://jobs.lever.co/cred/cred-job-1",
            "descriptionPlain": "Build backend APIs.",
            "lists": [{"text": "Requirements", "content": "<ul><li>Python and 3+ years experience</li></ul>"}],
            "additional": "<p>Work with CRED.</p>",
        }
        jobs = LeverAdapter({"name": "CRED", "site": "cred", "company": "CRED"}, FakeHttp([item])).fetch()
        self.assertEqual(jobs[0].external_id, "cred-job-1")
        self.assertEqual(jobs[0].company, "CRED")
        self.assertEqual(jobs[0].url, item["hostedUrl"])
        self.assertIn("3+ years experience", jobs[0].description)
        self.assertIn("Work with CRED.", jobs[0].description)

    def test_amazon_pagination_and_india_mapping(self):
        class AmazonHttp:
            def get_json(self, url):
                params = parse_qs(urlsplit(url).query)
                self_query = params["base_query"][0]
                offset = int(params["offset"][0])
                assert self_query == "software development engineer ii"
                item = {
                    "id_icims": str(100 + offset),
                    "title": "Software Development Engineer II",
                    "country_code": "IND",
                    "location": "IN, TS, Hyderabad",
                    "job_path": f"/en/jobs/{100 + offset}/software-development-engineer-ii",
                    "description": "<p>Build backend APIs</p>",
                    "basic_qualifications": "3+ years of non-internship experience",
                    "posted_date": "September 29, 2026",
                }
                return {"hits": 2, "jobs": [item]}

        jobs = AmazonAdapter({"name": "Amazon Jobs", "search_queries": ["software development engineer ii"],
                              "page_size": 1, "max_pages": 2}, AmazonHttp()).fetch()
        self.assertEqual([job.external_id for job in jobs], ["100", "101"])
        self.assertEqual(jobs[0].url, "https://www.amazon.jobs/en/jobs/100/software-development-engineer-ii")
        self.assertIn("Hyderabad, India", jobs[0].location)
        self.assertIn("non-internship experience", jobs[0].description)

    def test_greenhouse_mapping(self):
        http = FakeHttp({"jobs": [{"id": 7, "title": "Engineer", "absolute_url": "https://x/7",
                                    "location": {"name": "Remote"}, "content": "<p>Build APIs</p>",
                                    "updated_at": "2026-01-01"}]})
        jobs = GreenhouseAdapter({"name": "Acme", "type": "greenhouse", "board_token": "acme"}, http).fetch()
        self.assertEqual(jobs[0].description, "Build APIs")
        self.assertEqual(jobs[0].external_id, "7")

    def test_generic_json_ld(self):
        html = '''<script type="application/ld+json">{"@type":"JobPosting","title":"Backend Engineer",
        "identifier":{"value":"abc"},"hiringOrganization":{"name":"Acme"},
        "jobLocation":{"address":{"addressLocality":"Bengaluru","addressCountry":"IN"}},
        "url":"https://example.test/abc","description":"<p>Python</p>","datePosted":"2026-01-01"}</script>'''
        jobs = GenericHtmlAdapter({"name": "Careers", "url": "https://example.test"}, FakeHttp(text=html)).fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Acme")
        self.assertIn("Bengaluru", jobs[0].location)


if __name__ == "__main__":
    unittest.main()
