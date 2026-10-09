@echo off
title AvaliaIA - Painel de Avaliacao Imobiliaria
cd /d "%~dp0"
echo ========================================================
echo   Iniciando AvaliaIA - Painel Web de Avaliacao
echo ========================================================
echo.
echo Abrindo navegador em http://localhost:8501 ...
echo.
.\venv\Scripts\streamlit.exe run app.py
pause
