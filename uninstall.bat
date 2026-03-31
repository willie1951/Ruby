@echo off
:: 1. Administrative Elevation Check
net session >nul 2>&1
if %errorLevel% neq 0 (
	echo [ERROR] Please right-click and 'Run as Administrator'.
	pause
	exit /b
)

echo [ACTION] Stopping Macks background processes...

:: 2. Stop the listener and the brain to release file locks
taskkill /F /IM wake_ruby.exe /T >nul 2>&1
taskkill /F /IM ruby.exe /T >nul 2>&1

echo [ACTION] Removing Startup Registry Hook...

:: 3. Delete only the "RubyWake" key
:: This prevents Macks from starting automatically on next boot
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "RubyWake" /f >nul 2>&1

echo [COMPLETE] Macks is no longer linked to Windows Startup.
echo [INFO] You can now manually update the EXEs or delete the folder.
pause