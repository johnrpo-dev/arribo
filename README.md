# Arribo

Gestión de servicios de grúa: registro de solicitudes, asignación a conductores, seguimiento de cada
vehículo, cobro por pagador y control de documentos con vencimiento.

- `backend/`: Django + PostgreSQL. Panel web y API.
- `conductor/`: app Flutter para Android (se crea en la tarea 1a-01; ver `conductor/README.md`).
- `docs/`: arquitectura, tareas de la fase 1a y checklist de prueba sin señal.
- `CLAUDE.md`: instrucciones para trabajar el proyecto con Claude Code.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala Python y las dependencias).
- PostgreSQL para desarrollo real. Sin `DATABASE_URL` el esqueleto arranca con SQLite.
- Flutter, para la app del conductor.

## Instalar y ejecutar

```
cd backend
uv sync
uv run pytest -q
uv run python manage.py migrate
uv run python manage.py runserver
```

Abrir http://127.0.0.1:8000/salud/ : debe responder `{"estado": "ok", "servicio": "arribo"}`.

Para configurar el entorno, copiar `.env.example` a `.env` en la raíz y completar los valores.
