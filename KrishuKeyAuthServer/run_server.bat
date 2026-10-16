@echo off
title Krishu KeyAuth API Server
cls
color 0C
echo ================================================================
echo             KRISHU KEYAUTH CLOUD API SERVER (v1)
echo ================================================================
echo.
echo [*] Memulai Krishu KeyAuth API Server...
echo [*] API URL untuk Cheat Form1 : http://localhost:5000/api/v1
echo [*] Web Admin Dashboard       : http://localhost:5000/
echo [*] Akun Default Cheat        : User='garaa' ^| Pass='123456'
echo.
echo Tekan Ctrl+C di terminal ini jika ingin mematikan server.
echo ================================================================
echo.
python server.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Gagal menjalankan python. Pastikan Python sudah terinstall!
    pause
)
