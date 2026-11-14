@echo off
rem BCIKit native WiFi receiver launcher (Windows Python).
rem The board AP has no internet and WSL2 NAT cannot receive the device's
rem outbound TCP connection, so the receiver runs on the Windows side.
rem
rem Usage:
rem   run_native_windows.bat <outdir> [receiver args...]
rem Example:
rem   run_native_windows.bat D:\physarum-data\native_N1_test --duration 600 --profile short
setlocal
set PY=D:\phy\python.exe
set SCRIPT=\\wsl.localhost\Ubuntu\path\to\physarum-lab\host\bcikit_native.py
if "%~1"=="" (
  echo Usage: %~nx0 ^<outdir^> [receiver args...]
  echo Example: %~nx0 D:\physarum-data\native_N1_test --duration 600 --profile short
  exit /b 2
)
"%PY%" "%SCRIPT%" --outdir %*
