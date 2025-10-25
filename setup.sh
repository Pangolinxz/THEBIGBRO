
set -e

echo " Iniciando configuración del proyecto LogiTrace"

PROJECT_DIR="Proyecto"

echo " Verificando entorno virtual ($PROJECT_DIR/.venv)..."
if [ ! -d "$PROJECT_DIR/.venv" ]; then
  python -m venv "$PROJECT_DIR/.venv"
  echo " Entorno virtual creado en $PROJECT_DIR/.venv"
else
  echo " Entorno virtual ya existente."
fi

echo " Activando entorno virtual..."
source "$PROJECT_DIR/.venv/bin/activate" || source "$PROJECT_DIR/.venv/Scripts/activate"

echo " Instalando dependencias desde requirements.txt..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
else
  echo " No se encontró requirements.txt, instalando dependencias básicas..."
  pip install django mysqlclient python-dotenv
fi

echo " Levantando contenedor Docker (MySQL)..."
docker compose up -d || docker-compose up -d
echo " Esperando que el contenedor esté listo..."
sleep 15

echo " Verificando estado del contenedor..."
docker compose ps || docker-compose ps

echo " Aplicando migraciones Django..."
python "$PROJECT_DIR/manage.py" makemigrations || true
python "$PROJECT_DIR/manage.py" migrate --fake-initial || true

echo " Ejecutando prueba de configuración..."
python "$PROJECT_DIR/manage.py" check

echo " Iniciando servidor Django en http://127.0.0.1:8000/"
python "$PROJECT_DIR/manage.py" runserver

echo " Proyecto LogiTrace configurado correctamente."
echo "   Usa 'source $PROJECT_DIR/.venv/bin/activate' para activar el entorno virtual."
