import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
"""
tests/test_matcher - Matcher and Scoring Unit Tests
"""
import unittest
from career_pipeline.models import CandidatePersona
from career_pipeline.evaluator.matcher import evaluate_job

class TestMatcher(unittest.TestCase):
    def setUp(self):
        self.persona = CandidatePersona(
            name="Test Candidate",
            target_locations=["munich", "remote", "germany"],
            excluded_locations=["london", "tokyo"],
            dealbreaker_keywords=["junior", "intern", "praktikum"],
            pillars=[
                {"name": "Robotics & Perception", "weight": 20, "keywords": ["robotics", "lidar", "perception"]},
                {"name": "Software Systems", "weight": 15, "keywords": ["python", "architecture", "c++"]}
            ]
        )

    def test_dealbreaker_filtering(self):
        posting = {
            "id": "1",
            "title": "Junior Robotics Intern",
            "company": "Tech Corp",
            "location": "Munich, Germany",
            "raw_content": "Exciting internship opportunity in lidar."
        }
        res = evaluate_job(posting, self.persona)
        self.assertLess(res["fit_score"], 50)
        self.assertTrue(len(res["gaps_risks"]) > 0)

    def test_high_fit_scoring(self):
        posting = {
            "id": "2",
            "title": "Lead Robotics & Perception Architect",
            "company": "Tech Corp",
            "location": "Munich, Germany",
            "raw_content": "Leading architecture of robotics perception pipelines with lidar and python."
        }
        res = evaluate_job(posting, self.persona)
        self.assertGreaterEqual(res["fit_score"], 80)
        self.assertIn("Robotics & Perception", res["matching_pillars"])

if __name__ == "__main__":
    unittest.main()
