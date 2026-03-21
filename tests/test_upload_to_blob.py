import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "RAG API" / "external_utils.py"


def load_external_utils_module():
    spec = importlib.util.spec_from_file_location("external_utils_test_module", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class UploadToBlobTests(unittest.TestCase):
    def test_s3_upload_uses_local_temp_file_when_stream_is_closed(self):
        external_utils = load_external_utils_module()
        fake_upload = SimpleNamespace(
            filename="sample.pdf",
            content_type="application/pdf",
            file=io.BytesIO(b"request-stream-bytes"),
        )
        fake_upload.file.close()

        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"temp-file-bytes")
            temp_file_path = handle.name

        mock_s3 = MagicMock()
        captured = {}

        def fake_upload_fileobj(fileobj, bucket, key):
            captured["body"] = fileobj.read()
            captured["bucket"] = bucket
            captured["key"] = key

        mock_s3.upload_fileobj.side_effect = fake_upload_fileobj

        with patch.object(external_utils, "get_config", return_value={"vector_store": "s3", "aws_region": "ap-south-1", "s3_bucket_documents": "bucket"}):
            with patch.object(external_utils.boto3, "client", return_value=mock_s3):
                result = external_utils.upload_to_blob(
                    fake_upload,
                    storage_account_name="unused",
                    container_name="Project/test-index",
                    local_file_path=temp_file_path,
                )

        self.assertTrue(result)
        mock_s3.upload_fileobj.assert_called_once()
        self.assertEqual(captured["bucket"], "bucket")
        self.assertEqual(captured["key"], "Project/test-index/sample.pdf")
        self.assertEqual(captured["body"], b"temp-file-bytes")


if __name__ == "__main__":
    unittest.main()
