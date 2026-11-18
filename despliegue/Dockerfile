# Imagen del servidor de Arribo (panel, API y tareas de cada minuto). Se construye desde la raíz
# del repositorio: docker compose lo hace con `despliegue/desplegar.sh`.
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    ARRIBO_DEBUG=0 \
    ARRIBO_MEDIA_ROOT=/datos/media \
    ARRIBO_STATIC_ROOT=/datos/estaticos

WORKDIR /app

# Primero solo las dependencias: si el código cambia y ellas no, Docker reutiliza esta capa.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/ ./
COPY despliegue/servidor.sh despliegue/tareas.sh /usr/local/bin/

# Sin privilegios de administrador. Las carpetas de datos se crean aquí con su dueño para que los
# volúmenes de Docker nazcan con ese mismo dueño. El número 10001 es fijo: la carpeta de secretos
# del servidor se le entrega a ese usuario (docs/despliegue.md).
RUN useradd --system --uid 10001 --no-create-home arribo \
    && mkdir -p /datos/media /datos/estaticos \
    && chown -R arribo /datos
USER arribo

EXPOSE 8000
CMD ["sh", "/usr/local/bin/servidor.sh"]
