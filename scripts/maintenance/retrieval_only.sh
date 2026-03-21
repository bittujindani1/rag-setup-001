set -e
cd '/c/Users/dhairya.jindani/Documents/AI-coe projects/Rag'
export AWS_PROFILE='default'
export PYTHONPATH="$(pwd)"
.venv_local/Scripts/python - <<'PY'
import requests

base_url = 'http://127.0.0.1:8000'
index_name = 'smoke-test-index'
session_id = 'retrieval-only-check'
query = 'What does this document describe?'

health = requests.get(f'{base_url}/health', timeout=15)
health.raise_for_status()
print('HEALTH', health.json())

query_resp = requests.post(
    f'{base_url}/SFRAG/retrieval',
    json={'user_query': query, 'index_name': index_name, 'session_id': session_id},
    timeout=1200,
)
print('QUERY_STATUS_CODE', query_resp.status_code)
print('QUERY_BODY', query_resp.text)
query_resp.raise_for_status()
PY
