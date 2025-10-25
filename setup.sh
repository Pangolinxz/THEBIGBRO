
set -e

echo " Iniciando configuración del proyecto LogiTrace..."

PROJECT_DIR="Proyecto"
VENV_DIR="$PROJECT_DIR/.venv"

echo "🔍 Verificando entorno virtual en $VENV_DIR ..."
if [ ! -d "$VENV_DIR" ]; then
    echo " Creando entorno virtual..."
    python3 -m venv "$VENV_DIR"
    echo " Entorno virtual creado."
else
    echo "ℹ Entorno virtual ya existente."
fi

echo " Activando entorno virtual..."
source "$VENV_DIR/bin/activate"

echo " Instalando dependencias desde requirements.txt..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "⚠ No se encontró requirements.txt, instalando dependencias básicas..."
    pip install django mysqlclient python-dotenv
fi

echo " Levantando contenedores Docker..."
docker compose up -d || docker-compose up -d

echo " Esperando que la base de datos esté lista..."
sleep 20

echo "🔎 Verificando contenedores activos..."
docker compose ps || docker-compose ps

echo "⚙ Aplicando migraciones Django..."
python "$PROJECT_DIR/manage.py" makemigrations
python "$PROJECT_DIR/manage.py" migrate --fake-initial

echo " Comprobando configuración Django..."
python "$PROJECT_DIR/manage.py" check

echo " Iniciando servidor Django en http://127.0.0.1:8000/"
python "$PROJECT_DIR/manage.py" runserver 0.0.0.0:8000

echo " Proyecto LogiTrace listo para desarrollo."
