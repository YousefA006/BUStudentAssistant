@echo off
cd /d "%~dp0"
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo A settings file .env was created. Paste your Anthropic API key after ANTHROPIC_API_KEY=
  echo then save, close Notepad and run this file again.
  notepad .env
  pause
  exit /b
)
findstr /c:"ANTHROPIC_API_KEY=your-key-here" .env >nul && (
  echo Please put your Anthropic API key in the .env file first.
  notepad .env
  pause
  exit /b
)
if not exist .venv (
  echo Creating virtual environment...
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing requirements...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
echo.
echo Starting Bethlehem University Student Assistant...
python app.py
pause
