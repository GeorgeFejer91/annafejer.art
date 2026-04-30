@echo off
setlocal

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0compile-assets\scripts\build_portfolio_pipeline.ps1" -Language de
if errorlevel 1 (
  echo.
  echo Deutsche A4-Portfolio-PDF-Kompilierung fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo Deutsche A4-Portfolio-PDF-Kompilierung abgeschlossen.
pause
exit /b 0
