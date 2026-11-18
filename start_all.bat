@echo off
echo ==========================================================
echo Starting AAISE Platform (Backend + Frontend)
echo ==========================================================

echo Starting FastAPI Backend (Port 8081)...
start "AAISE Backend" cmd /k ".venv\Scripts\python.exe run_backend.py"

echo Starting Next.js Frontend (Port 8080)...
start "AAISE Frontend" cmd /k "cd frontend && npm run dev"

echo ==========================================================
echo Services are launching!
echo Frontend: http://localhost:8080
echo Backend API Docs: http://localhost:8081/docs
echo ==========================================================
pause
