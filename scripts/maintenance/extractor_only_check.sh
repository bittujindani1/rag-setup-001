set -e
cd '/c/Users/dhairya.jindani/Documents/AI-coe projects/Rag'
export PYTHONPATH="$(pwd)"
.venv_local/Scripts/python - <<'PY'
import json
import tempfile
from pathlib import Path
import importlib.util

root = Path.cwd()
module_path = root / 'RAG API' / 'external_utils.py'
spec = importlib.util.spec_from_file_location('external_utils_runtime', module_path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

pdf_path = Path(r'C:\Users\dhairya.jindani\Downloads\sample_travel_insurance_policy_test.pdf')
with tempfile.TemporaryDirectory() as temp_dir:
    result = module.process_file(str(pdf_path), 'extractor-smoke', temp_dir)
    page_keys = [k for k in result.keys() if k.isdigit()]
    print('EXTRACTOR_OK')
    print('PAGE_COUNT', len(page_keys))
    print('TOP_LEVEL_KEYS', list(result.keys())[:10])
    sample_key = page_keys[0] if page_keys else None
    if sample_key:
        sample = result[sample_key]
        print('FIRST_PAGE_KEYS', list(sample.keys())[:10])
        print('FIRST_PAGE_HAS_BBOXES', 'bboxes_info' in sample)
PY
