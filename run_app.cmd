@echo off
REM Windows one-click launcher: installs uv if missing, seeds .env when needed,
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

REM Configured environment credentials need no .env file. Never overwrite one.
if not defined OPENAI_API_KEY if not exist ".env" (
    if exist ".env.example" (
        echo No .env found - copying .env.example as a starting point.
        copy /y ".env.example" ".env" >nul
        echo Edit .env with your OPENAI_API_KEY if it is not already set system-wide.
    )
)

if not defined OPENAI_API_KEY (
    echo [WARNING] OPENAI_API_KEY is not set in your environment.
    echo Set it in .env or the system environment before using the app.
)

echo Installing/updating dependencies with uv...
uv sync
if errorlevel 1 (
    echo [ERROR] uv sync failed. See the output above.
    pause
    exit /b 1
)

echo Clearing port 7080...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\clear_app_port.ps1" -Port 7080
if errorlevel 1 (
    echo [ERROR] Could not clear port 7080. The app was not started.
    pause
    exit /b 1
)

echo Starting the Self-Improving Prompt Optimizer at http://localhost:7080 ...
REM Pin the same port that was cleared, even if an environment override is set.
uv run streamlit run app.py --server.port 7080 --theme.base dark

pause
