@echo off
title AvaliaIA Pro - Painel Web com Tunel Cloudflare
cd /d "%~dp0"
echo ========================================================
echo   Iniciando AvaliaIA Pro - Painel Web com Tunel Publico
echo ========================================================
echo.
echo [1/2] Iniciando aplicacao Streamlit em segundo plano...
start "Streamlit Local" /B .\venv\Scripts\streamlit.exe run app.py --server.headless true --server.port 8501

echo [2/2] Conectando tunel Cloudflare (HTTPS gratuito e seguro)...
echo Aguarde 5 segundos enquanto o link publico eh gerado...
timeout /t 5 /nobreak >nul
echo.
echo ========================================================
echo   ACESSO PUBLICO NA WEB:
echo   Copie o link 'https://....trycloudflare.com' abaixo
echo ========================================================
echo.
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8501
pause
