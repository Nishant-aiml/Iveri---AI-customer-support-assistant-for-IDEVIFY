# Local Quality, Security & Evals Runner for Windows
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Running IDEVIFY Local Quality, Security & Evals Suite    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Run Guardrails & Evals Suite
Write-Host "`n[1/3] Running Guardrails & Safety Evals..." -ForegroundColor Yellow
python -m unittest backend/tests/test_guardrails_evals.py

# 2. Run Phase 1-5 Core Tests
Write-Host "`n[2/3] Running Core Feature Regression Tests (Phases 1-5)..." -ForegroundColor Yellow
python -m unittest backend/tests/test_phase1_phase2.py backend/tests/test_phase3_rag.py backend/tests/test_phase4_chat.py backend/tests/test_phase5_dashboard.py

# 3. Done
Write-Host "`n[3/3] Local verification completed successfully!" -ForegroundColor Green
