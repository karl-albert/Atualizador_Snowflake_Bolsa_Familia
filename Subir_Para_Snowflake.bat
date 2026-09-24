@echo off
chcp 65001 >nul
title Carga Bolsa Família para Snowflake (GUI)
cd /d "%~dp0"
echo =========================================================================
echo  Iniciando Aplicativo de Ingestao Snowflake - Bolsa Familia...
echo =========================================================================
python "app_upload_snowflake_gui.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [AVISO] Ocorreu uma excecao ao rodar a GUI. Verifique se o Python esta instalado.
    pause
)
