import importlib.util
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "RAG API" / "external_utils.py"


def load_external_utils_module():
    spec = importlib.util.spec_from_file_location("external_utils_contract_module", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class DocumentExtractorContractTests(unittest.TestCase):
    def test_structured_pages_are_translated_to_legacy_payload(self):
        external_utils = load_external_utils_module()
        pages = [
            {
                "page_number": 1,
                "text": "Travel insurance coverage summary",
                "images": ["https://bucket.s3.ap-south-1.amazonaws.com/fig1.png"],
                "tables": [
                    {
                        "text": "Benefit | Amount\nTrip Delay | $500",
                        "image_url": "https://bucket.s3.ap-south-1.amazonaws.com/table1.png",
                    }
                ],
                "page_image_url": "https://bucket.s3.ap-south-1.amazonaws.com/page1.png",
            }
        ]

        payload = external_utils._structured_pages_to_legacy_json(
            pages,
            "sample.pdf",
            "https://documents.example/sample.pdf",
        )

        self.assertIn("1", payload)
        self.assertEqual(payload["file_name"], "sample.pdf")
        self.assertEqual(payload["input_file_url"], "https://documents.example/sample.pdf")
        self.assertEqual(payload["1"]["bbox_img_url"], "https://bucket.s3.ap-south-1.amazonaws.com/page1.png")

        bboxes = payload["1"]["bboxes_info"]
        self.assertEqual(bboxes[0]["label"], "TEXT")
        self.assertEqual(bboxes[0]["output"], "Travel insurance coverage summary")
        self.assertEqual(bboxes[1]["label"], "FIGURE")
        self.assertEqual(bboxes[1]["img_url"], "https://bucket.s3.ap-south-1.amazonaws.com/fig1.png")
        self.assertEqual(bboxes[2]["label"], "TABLE")
        self.assertIn("Trip Delay", bboxes[2]["output"])
        self.assertEqual(bboxes[2]["img_url"], "https://bucket.s3.ap-south-1.amazonaws.com/table1.png")


if __name__ == "__main__":
    unittest.main()
