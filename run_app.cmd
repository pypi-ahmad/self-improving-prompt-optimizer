@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo "uv" not found, installing it now...
    powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

if not exist ".env" (
    if exist ".env.example" (
        echo No .env found - copying .env.example as a starting point.
        copy /y ".env.example" ".env" >nul
        echo Edit .env with your OPENAI_API_KEY if it is not already set system-wide.
    )
)

if "%OPENAI_API_KEY%"=="" (
    echo [WARNING] OPENAI_API_KEY is not set in your environment.
    echo The app will fail to call the model until it is set (in .env or system-wide).
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
