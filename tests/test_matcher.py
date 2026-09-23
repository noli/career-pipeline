"""
tests/test_matcher - Multi-Region Matcher and Scoring Unit Tests
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest
from career_pipeline.models import CandidatePersona
from career_pipeline.evaluator.matcher import evaluate_job

class TestMatcher(unittest.TestCase):
    def setUp(self):
        self.persona = CandidatePersona(
            name="Test Candidate",
            target_locations=["munich", "remote", "germany"],
            excluded_locations=["berlin", "london", "tokyo"],
            dealbreaker_keywords=["junior", "intern", "praktikum"],
            pillars=[
                {"name": "Robotics & Perception", "weight": 20, "keywords": ["robotics", "lidar", "perception"]},
                {"name": "Software Systems", "weight": 15, "keywords": ["python", "architecture", "c++"]}
            ],
            regions={
                "munich": {
                    "name": "Munich Metropolitan Area",
                    "target_locations": ["munich", "münchen", "garching", "remote", "germany"],
                    "excluded_locations": ["berlin", "london", "tokyo"]
                },
                "berlin": {
                    "name": "Berlin-Brandenburg Area",
                    "target_locations": ["berlin", "potsdam", "remote", "germany"],
                    "excluded_locations": ["munich", "münchen", "london", "tokyo"]
                }
            }
        )

    def test_dealbreaker_filtering(self):
        posting = {
            "id": "1",
            "title": "Junior Robotics Intern",
            "company": "Tech Corp",
            "location": "Munich, Germany",
            "raw_content": "Exciting internship opportunity in lidar."
        }
        res = evaluate_job(posting, self.persona, region="munich")
        self.assertLess(res["fit_score"], 50)
        self.assertTrue(len(res["gaps_risks"]) > 0)

    def test_multi_region_separation(self):
        # Munich-only job
        munich_job = {
            "id": "2",
            "title": "Lead Robotics Architect",
            "company": "Munich Auto",
            "location": "Munich, Germany",
            "raw_content": "Lead our perception and lidar architecture in Munich using python and c++."
        }
        m_res = evaluate_job(munich_job, self.persona, region="munich")
        b_res = evaluate_job(munich_job, self.persona, region="berlin")
        self.assertGreaterEqual(m_res["fit_score"], 85)
        self.assertLess(b_res["fit_score"], 50)

        # Berlin-only job
        berlin_job = {
            "id": "3",
            "title": "Lead Robotics Architect",
            "company": "Berlin Quantum",
            "location": "Berlin, Germany",
            "raw_content": "Lead our perception and lidar architecture in Berlin using python and c++."
        }
        m_res_b = evaluate_job(berlin_job, self.persona, region="munich")
        b_res_b = evaluate_job(berlin_job, self.persona, region="berlin")
        self.assertLess(m_res_b["fit_score"], 50)
        self.assertGreaterEqual(b_res_b["fit_score"], 85)

    def test_remote_job_scores_in_both_regions(self):
        remote_job = {
            "id": "4",
            "title": "Principal AI & Robotics Architect",
            "company": "Remote AI Labs",
            "location": "Remote, Germany",
            "workplace_type": "remote",
            "raw_content": "100% remote role leading robotics, perception, and lidar architecture in python and c++."
        }
        m_res = evaluate_job(remote_job, self.persona, region="munich")
        b_res = evaluate_job(remote_job, self.persona, region="berlin")
        self.assertGreaterEqual(m_res["fit_score"], 85)
        self.assertGreaterEqual(b_res["fit_score"], 85)
        self.assertIn("compensation_estimate", m_res)
        self.assertGreaterEqual(m_res["compensation_estimate"]["base_salary_min"], 120000)

if __name__ == "__main__":
    unittest.main()
