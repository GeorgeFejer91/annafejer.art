@echo off
setlocal

cd /d "%~dp0"

echo.
echo Publishing local commits to GitHub main...
echo.

git status --short
echo.

git fetch origin --prune
if errorlevel 1 (
  echo.
  echo Could not fetch from GitHub.
  pause
  exit /b 1
)

git pull --rebase origin main
if errorlevel 1 (
  echo.
  echo Could not rebase onto the current GitHub main branch.
  echo Resolve the conflict, then run this file again.
  pause
  exit /b 1
)

git push origin main
if errorlevel 1 (
  echo.
  echo Push failed. Check GitHub Desktop/sign-in permissions.
  pause
  exit /b 1
)

echo.
echo GitHub main now has this version:
git log -1 --oneline --decorate
echo.
pause
exit /b 0
