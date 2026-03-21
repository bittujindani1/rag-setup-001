set -e
cd '/c/Users/dhairya.jindani/Documents/AI-coe projects/Rag'
export AWS_PROFILE='default'
export PYTHONPATH="$(pwd)"
.venv_local/Scripts/python - <<'PY'
from pathlib import Path
import requests

base_url = 'http://127.0.0.1:8000'
pdf_path = Path(r'C:\Users\dhairya.jindani\Downloads\sample_travel_insurance_policy_test.pdf')
index_name = 'smoke-test-index'
session_id = 'single-e2e-session-postfix'
query = 'What does this document describe?'

health = requests.get(f'{base_url}/health', timeout=15)
health.raise_for_status()
print('HEALTH', health.json())

with pdf_path.open('rb') as handle:
    ingest = requests.post(
        f'{base_url}/SFRAG/ingest',
        data={'index_name': index_name},
        files={'file': (pdf_path.name, handle, 'application/pdf')},
        timeout=900,
    )
print('INGEST_STATUS_CODE', ingest.status_code)
print('INGEST_BODY', ingest.text)
ingest.raise_for_status()

ingest_payload = ingest.json()
if ingest_payload.get('status') != 'Index ingested successfully':
    raise SystemExit(f'Unexpected ingest response: {ingest_payload}')

query_resp = requests.post(
    f'{base_url}/SFRAG/retrieval',
    json={'user_query': query, 'index_name': index_name, 'session_id': session_id},
    timeout=900,
)
print('QUERY_STATUS_CODE', query_resp.status_code)
print('QUERY_BODY', query_resp.text)
query_resp.raise_for_status()

payload = query_resp.json()
assert isinstance(payload.get('response', {}).get('content'), str)
assert isinstance(payload.get('citation'), list)
print('E2E_OK')
PY
