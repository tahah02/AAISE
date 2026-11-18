Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Starting AAISE Platform (Backend + Frontend)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Launch Backend
Write-Host "Launching FastAPI Backend (Port 8081)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host 'AAISE Backend Running...' -ForegroundColor Green; .venv\Scripts\python.exe run_backend.py"

# Launch Frontend
Write-Host "Launching Next.js Frontend (Port 8080)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host 'AAISE Frontend Running...' -ForegroundColor Yellow; Set-Location frontend; npm run dev"

Write-Host "`nServices are launching:" -ForegroundColor Cyan
Write-Host "👉 Frontend UI:        http://localhost:8080" -ForegroundColor White
Write-Host "👉 Backend Swagger UI:  http://localhost:8081/docs" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan
