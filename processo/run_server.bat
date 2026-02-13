@echo off
SETLOCAL EnableDelayedExpansion
TITLE Kyro Server - NAO FECHE
color 0A

:: 1. Limpeza forçada se existir e estiver corrompido
IF EXIST ".venv" (
    echo [INFO] Verificando ambiente virtual...
)

:: 2. Criação Segura
IF NOT EXIST ".venv" (
    echo [INFO] Criando ambiente Python seguro...
    python -m venv .venv
    
    echo [INFO] Instalando bibliotecas...
    call .venv\Scripts\activate.bat
    pip install fastapi uvicorn pdfplumber pandas python-multipart
) ELSE (
    call .venv\Scripts\activate.bat
)

:: 3. Execução
echo.
echo =========================================
echo    SERVIDOR ONLINE: http://localhost:8000
echo    MANTENHA ESTA JANELA ABERTA
echo =========================================
echo.
uvicorn api_extracao:app --reload --host 127.0.0.1 --port 8000
pause
