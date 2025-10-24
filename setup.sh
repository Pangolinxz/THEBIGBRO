
set -e

echo 


echo "📦 Verificando entorno virtual (.venv)..."
if [ ! -d ".venv" ]; then
  python -m venv .venv
  echo "✅ Entorno virtual creado."
else
  echo "ℹ️ Entorno virtual ya existente."
fi

echo "⚙️ Activando entorno virtual..."
source .venv/bin/activate || source .venv/Scripts/activate


echo "📚 Instalando dependencias desde requirements.txt..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
else
  echo "⚠️ No se encontró requirements.txt, instalando dependencias básicas..."
  pip install django mysqlclient python-dotenv
fi


echo "🐳 Levantando contenedor Docker (MySQL)..."
docker compose up -d || docker-compose up -d
echo "⏳ Esperando que el contenedor esté listo..."
sleep 15


echo "🔍 Verificando estado del contenedor..."
docker compose ps || docker-compose ps


echo "🛠️ Aplicando migraciones Django..."
python manage.py makemigrations || true
python manage.py migrate --fake-initial || true


echo "🧪 Ejecutando prueba de configuración..."
python manage.py check

echo "🚀 Iniciando servidor Django en http://127.0.0.1:8000/"
python manage.py runserver


echo "✅ Proyecto LogiTrace configurado correctamente."
echo "   Usa 'source .venv/bin/activate' para activar el entorno."
