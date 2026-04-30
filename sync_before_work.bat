@echo off
setlocal

cd /d "%~dp0"

echo.
echo Syncing this repository to the current GitHub main branch...
echo.

git status --porcelain > "%TEMP%\annafejer_git_status.txt"
for %%A in ("%TEMP%\annafejer_git_status.txt") do set STATUS_SIZE=%%~zA
if not "%STATUS_SIZE%"=="0" (
  echo Your working tree has local changes.
  echo Commit, push, or stash them before syncing so no work is lost.
  echo.
  git status --short
  del "%TEMP%\annafejer_git_status.txt" >nul 2>nul
  pause
  exit /b 1
)
del "%TEMP%\annafejer_git_status.txt" >nul 2>nul

git switch main
if errorlevel 1 (
  echo.
  echo Could not switch to main.
  pause
  exit /b 1
)

git fetch origin --prune
if errorlevel 1 (
  echo.
  echo Could not fetch from GitHub.
  pause
  exit /b 1
)

git pull --ff-only origin main
if errorlevel 1 (
  echo.
  echo Could not fast-forward to origin/main.
  echo Ask George/Anna to check whether there are conflicting local commits.
  pause
  exit /b 1
)

echo.
echo Repository is now synced to:
git log -1 --oneline --decorate
echo.
pause
exit /b 0
