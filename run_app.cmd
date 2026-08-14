@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] "uv" was not found on PATH.
    echo Install it from https://docs.astral.sh/uv/ then re-run this file.
    pause
    exit /b 1
)

if "%OPENAI_API_KEY%"=="" (
    echo [WARNING] OPENAI_API_KEY is not set in your environment.
    echo The app will fail to call the model until it is set.
)

echo Installing/updating dependencies with uv...
uv sync
if errorlevel 1 (
    echo [ERROR] uv sync failed. See the output above.
    pause
    exit /b 1
)

echo Starting the Self-Improving Prompt Optimizer...
uv run streamlit run app.py --server.port 8531

pause
