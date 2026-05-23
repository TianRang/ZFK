@echo off
echo ================================
echo   ZFK - Build EXE
echo ================================
echo.

pip install pyinstaller >nul 2>&1

echo Building...
echo.

pyinstaller --onefile --name zfk --icon=static/icon.ico --add-data "templates;templates" --add-data "static;static" --add-data ".env.example;." --collect-data captcha --hidden-import aiosqlite --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on run.py

if %errorlevel% neq 0 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo ================================
echo   Done! Output: dist\zfk.exe
echo ================================
echo.
pause
