# Vivid Layout Generator — Python Version

Same as server.js but in Python/FastAPI. Runs on port 8000.

## Setup

1. Copy these files to D:\AI_Projects_Python\
2. Also copy from D:\AI_Projects\:
   - CLAUDE_SIMPLE.md
   - CLAUDE_IMAGE.md  
   - run_claude.bat
   - index.html (change SERVER_FILES to localhost:8000)

3. Install Python dependencies:
   pip install -r requirements.txt

4. Run:
   uvicorn server:app --port 8000 --reload

## Endpoints (same as server.js)

POST /api/run       ← called by UI (SSE streaming)
POST /api/generate  ← called by n8n
POST /api/save-db   ← Oracle DB save
GET  /api/files     ← list JSON files
GET  /api/file/{n}  ← get specific file

## n8n flow

Import n8n_python_flow.json
Only difference from JS flow:
  Generate Vivid JSON node URL = http://localhost:8000/api/generate
