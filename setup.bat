@echo off
setlocal enabledelayedexpansion

echo  Iniciando configuración del proyecto LogiTrace...

set PROJECT_DIR=Proyecto
set VENV_DIR=%PROJECT_DIR%\.venv

echo  Verificando entorno virtual en %VENV_DIR%...
if not exist "%VENV_DIR%" (
    echo  Creando entorno virtual...
    python -m venv "%VENV_DIR%"
    echo  Entorno virtual creado.
) else (
    echo ℹ Entorno virtual ya existente.
)

echo  Activando entorno virtual...
call "%VENV_DIR%\Scripts\activate.bat"

echo  Instalando dependencias desde requirements.txt...
python -m pip install --upgrade pip
if exist "requirements.txt" (
    python -m pip install -r requirements.txt
) else (
    echo  No se encontró requirements.txt, instalando dependencias básicas...
    python -m pip install django mysqlclient python-dotenv
)

echo  Levantando contenedores Docker...
docker compose up -d || docker-compose up -d

echo  Esperando que la base de datos esté lista...
timeout /t 20 >nul

echo  Verificando contenedores activos...
docker compose ps || docker-compose ps

echo  Aplicando migraciones Django...
python "%PROJECT_DIR%\manage.py" makemigrations
python "%PROJECT_DIR%\manage.py" migrate --fake-initial

echo  Comprobando configuración Django...
python "%PROJECT_DIR%\manage.py" check

echo  Iniciando servidor Django en http://127.0.0.1:8000/
python "%PROJECT_DIR%\manage.py" runserver

echo  Proyecto LogiTrace listo para desarrollo.
pause
