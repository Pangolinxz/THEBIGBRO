# Testing Linter (Flake8)

## Herramienta
- **Flake8** `>=7.0.0`
- Configuración en `setup.cfg`

```ini
[flake8]
max-line-length = 100
exclude = .git,__pycache__,.venv,Proyecto/.venv,Proyecto/tests/__pycache__
extend-ignore = E203,W503
```

## Ejecución
0. Instalar dependencias: `pip install -r requirements.txt`
1. Desde `Proyecto/` ejecutar: `flake8`
2. Capturar salida inicial (antes de corregir).
3. Corregir advertencias y volver a ejecutar `flake8`.

## Evidencias
- Capturas de consola con errores iniciales.
- Capturas/postcorrección sin errores.
- Descripción breve de las reglas y ajustes aplicados.

> Convertir este documento en PDF (Arial 11, estilo indicado por el curso) y guardarlo como `Documentación/Proyecto/testing_linter.pdf`.
