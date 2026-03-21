set -e
cd '/c/Users/dhairya.jindani/Documents/AI-coe projects/Rag'
export AWS_PROFILE='default'
export PYTHONPATH="$(pwd)"
.venv_local/Scripts/python - <<'PY'
import importlib.util
import json
import tempfile
from pathlib import Path

root = Path.cwd()
module_path = root / 'RAG API' / 'external_utils.py'
spec = importlib.util.spec_from_file_location('external_utils_runtime', module_path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

pdf_path = Path(r'C:\Users\dhairya.jindani\Downloads\sample_travel_insurance_policy_test.pdf')
input_file_url = 'https://example.invalid/sample_travel_insurance_policy_test.pdf'

with tempfile.TemporaryDirectory() as temp_dir:
    json_path = module.upload_pdf_and_download_json(
        str(pdf_path),
        30,
        temp_dir,
        pdf_path.name,
        input_file_url,
    )
    payload = json.loads(Path(json_path).read_text(encoding='utf-8'))
    page_keys = sorted([key for key in payload.keys() if key.isdigit()], key=int)
    print('EXTRACTOR_JSON_OK')
    print('JSON_PATH', json_path)
    print('PAGE_COUNT', len(page_keys))
    print('TOP_LEVEL_META', payload.get('file_name'), payload.get('input_file_url'))
    if page_keys:
        first_page = payload[page_keys[0]]
        bboxes = first_page.get('bboxes_info', [])
        print('FIRST_PAGE', page_keys[0])
        print('FIRST_PAGE_BBOX_COUNT', len(bboxes))
        print('FIRST_PAGE_HAS_PAGE_IMAGE', bool(first_page.get('bbox_img_url')))
        print('FIRST_PAGE_LABELS', [box.get('label') for box in bboxes[:10]])
        asset_urls = []
        if first_page.get('bbox_img_url'):
            asset_urls.append(first_page['bbox_img_url'])
        for box in bboxes:
            if box.get('img_url'):
                asset_urls.append(box['img_url'])
        print('FIRST_PAGE_ASSET_URLS', asset_urls[:5])
PY
