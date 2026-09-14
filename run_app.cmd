@echo off
REM Windows one-click launcher: installs uv if missing, seeds .env on first run,
REM then runs `uv sync` and starts the Streamlit app. See README.md's
REM "Installation & Setup" for the manual, any-OS equivalent of these steps.
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo "uv" not found, installing it now...
    powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    REM `set` only changes PATH for this script's own process, not the installer
    REM or any parent shell — needed so `uv sync` below can find the binary just
    REM installed without requiring a new terminal session.
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

REM Only runs when .env is absent, so an existing .env (and any values already
REM set in it) is never overwritten by re-running this script.
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
REM --server.port duplicates the port already pinned in .streamlit/config.toml;
REM unclear from this file why both are set.
uv run streamlit run app.py --server.port 8531

pause
