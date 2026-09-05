#!/bin/bash
# GRMT full environment setup — run once per fresh Studio instance.
# Installs all dependencies, starts every required service, seeds the
# admin account, applies any pending SQLite column migrations (safe/no-op
# if already present), starts both servers, and runs the full test suite
# so you know immediately whether the instance is genuinely ready.
set -e

echo "=== [1/8] Backend dependencies ==="
cd ~/grmt-platform/backend
pip install -r requirements.txt --break-system-packages --quiet

echo "=== [2/8] Frontend dependencies ==="
cd ~/grmt-platform/frontend
npm install

echo "=== [3/8] Seeding admin account ==="
cd ~/grmt-platform/backend
python -m app.scripts.seed_admin --username "Admin@GRMT" --password "24GRMT@2026"

echo "=== [4/8] Starting LanguageTool ==="
cd ~/LanguageTool-6.6
nohup java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8010 --allow-origin "*" > ~/languagetool.log 2>&1 &

echo "=== [5/8] Starting GROBID ==="
cd ~/grobid-0.8.1
nohup ./gradlew run --no-daemon > ~/grobid.log 2>&1 &

echo "=== [6/8] Installing and starting Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh
sleep 3
ollama pull qwen2.5:7b-instruct

echo "=== Waiting 40s for LanguageTool + GROBID to finish loading models ==="
sleep 40

echo "=== [7/8] Starting backend + frontend servers ==="
cd ~/grmt-platform/backend
nohup uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > ~/grmt-platform/backend.log 2>&1 &
cd ~/grmt-platform/frontend
nohup npm run dev > ~/grmt-platform/frontend.log 2>&1 &
sleep 8

echo ""
echo "=== Health checks ==="
echo -n "Backend:      "; curl -s http://localhost:8000/api/health
echo ""
echo -n "LanguageTool: "; curl -s http://localhost:8010/v2/check -d "text=test&language=en-US" | head -c 80
echo ""
echo -n "GROBID:       "; curl -s http://localhost:8070/api/isalive
echo ""
echo -n "Ollama:       "; curl -s http://localhost:11434/api/tags | head -c 80
echo ""

echo ""
echo "=== [8/8] Applying any pending SQLite column migrations (safe, idempotent) ==="
cd ~/grmt-platform/backend
python3 -c "
import sqlite3
conn = sqlite3.connect('grmt_dev.db')
cur = conn.cursor()
existing = [row[1] for row in cur.execute('PRAGMA table_info(submissions)').fetchall()]
to_add = [
    ('previously_rejected_disclosure', 'TEXT'),
    ('camera_ready_file_url', 'TEXT'),
    ('copyright_transfer_file_url', 'TEXT'),
    ('camera_ready_uploaded_at', 'DATETIME'),
]
for name, col_type in to_add:
    if name not in existing:
        cur.execute(f'ALTER TABLE submissions ADD COLUMN {name} {col_type}')
        print(f'[ok] added column: {name}')
    else:
        print(f'[skip] already present: {name}')
conn.commit()
conn.close()
"

echo ""
echo "=== Running full test suite ==="
cd ~/grmt-platform/backend
python3 -m pytest -v 2>&1 | tail -20

echo ""
echo "=== Setup complete ==="
echo "Remember: your Winston AI key must be re-entered in /admin-dashboard (not persisted across instances)."
