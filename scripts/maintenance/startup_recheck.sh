set -e
cd '/c/Users/dhairya.jindani/Documents/AI-coe projects/Rag/RAG API'
export AWS_PROFILE='default'
export PYTHONPATH='/c/Users/dhairya.jindani/Documents/AI-coe projects/Rag'
nohup ../.venv_local/Scripts/python -m uvicorn main:app --host 127.0.0.1 --port 8000 > ../.startup_recheck.log 2>&1 &
echo $! > ../.startup_recheck.pid
