@echo off
chcp 65001 > nul
title Atualizador Mensal Bolsa Família - Snowflake
color 0A

echo ================================================================================
echo   BOLSA FAMÍLIA ANALYTICS — ATUALIZADOR MENSAL SNOWFLAKE
echo ================================================================================
echo.

python "%~dp0atualizador_mensal_snowflake.py"

echo.
echo ================================================================================
echo   Processo finalizado. Pressione qualquer tecla para sair...
echo ================================================================================
pause > nul
