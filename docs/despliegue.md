# Despliegue de Arribo (tarea 1a-21)

Cómo poner Arribo en un servidor propio con HTTPS y cómo armar el APK firmado de los conductores.
Lo que hay que contratar y las claves las maneja el dueño; los comandos están listos para copiar.

Qué queda corriendo en el servidor (todo con Docker Compose, `despliegue/docker-compose.yml`):

| Servicio | Qué hace |
|---|---|
| `caddy` | Recibe el tráfico de internet, saca y renueva solo el certificado HTTPS, entrega los estáticos. |
| `web` | El panel y la API de la app (Django con gunicorn). Al arrancar aplica las migraciones. |
| `tareas` | Cada minuto: alertas por umbral y reintento de avisos push pendientes. |
| `db` | PostgreSQL 18. Sus datos viven en un volumen de Docker que sobrevive a los despliegues. |
| `respaldo` | Copia diaria de la base en `/opt/arribo/respaldos` (guarda las últimas 14). |

Las fotos y documentos quedan en el volumen `media` del servidor (fase 1a).

## 1. Lo que contrata el dueño

1. **Un VPS** con Ubuntu 24.04, al menos 2 GB de RAM, 2 núcleos y 40 GB de disco. Sirve cualquier
   proveedor (Hetzner, DigitalOcean, Vultr, Contabo...). Al crearlo, agregue su llave SSH. Anote
   la IP pública.
2. **Un dominio** (o un subdominio de uno que ya tenga), por ejemplo `arribo.suempresa.co`. En el
   proveedor del dominio cree un registro **A** con ese nombre que apunte a la IP del VPS. Puede
   tardar unos minutos en propagarse; se comprueba con `ping arribo.suempresa.co`.

## 2. Preparar el servidor (una sola vez)

Entrar por SSH (`ssh root@IP-DEL-VPS`) y correr:

```bash
curl -fsSL https://get.docker.com | sh
```

```bash
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

```bash
mkdir -p /opt/arribo/secretos /opt/arribo/respaldos && chmod 700 /opt/arribo/secretos
```

```bash
git clone https://github.com/johnrpo-dev/arribo.git /opt/arribo/codigo
```

Si el repositorio es privado, GitHub pide usuario y token: cree un token de solo lectura en GitHub
(Settings → Developer settings → Fine-grained tokens, con acceso solo de lectura a `arribo`).

### Cuenta de servicio de Firebase (avisos push)

Desde su PC, copie el JSON de la cuenta de servicio al servidor (nunca al repositorio):

```bash
scp "C:\Users\USUARIO\Documents\arribo\cuenta-de-servicio.json" root@IP-DEL-VPS:/opt/arribo/secretos/
```

Y en el servidor, entregarle la carpeta al usuario sin privilegios con que corre Arribo (el 10001)
y cerrarla para los demás:

```bash
chown -R 10001 /opt/arribo/secretos && chmod 700 /opt/arribo/secretos && chmod 600 /opt/arribo/secretos/*.json
```

### El archivo de entorno

```bash
cd /opt/arribo/codigo/despliegue && cp .env.ejemplo .env && nano .env
```

Complete:

- `ARRIBO_DOMINIO`: el dominio, sin `https://`.
- `ARRIBO_SECRET_KEY`: el resultado de `openssl rand -base64 48`.
- `POSTGRES_PASSWORD`: el resultado de `openssl rand -hex 24`.
- `ARRIBO_FIREBASE_CREDENCIALES=/run/secretos/cuenta-de-servicio.json` (o vacío, sin push).

Guarde una copia de ese `.env` fuera del servidor (gestor de contraseñas): sin la clave de la base
no se recuperan los respaldos.

## 3. Desplegar

En el servidor, cada vez (la primera y en cada actualización):

```bash
cd /opt/arribo/codigo/despliegue && ./desplegar.sh
```

Trae lo último de `main`, reconstruye, levanta todo y termina comprobando
`https://DOMINIO/salud/`. La primera vez tarda unos minutos (descarga imágenes y saca el
certificado). Si termina con "Arribo desplegado en https://...", está listo.

Después del primer despliegue, cree el administrador del panel (pide usuario y contraseña):

```bash
cd /opt/arribo/codigo/despliegue && docker compose exec web python manage.py createsuperuser
```

Entre a `https://DOMINIO/` con ese usuario. Desde Flota y personal se crean los demás usuarios,
las grúas y los conductores (con su PIN).

## 4. El APK de los conductores (en el PC)

Una sola vez, crear la llave de firma (pide una clave; deja el `.jks` en
`Documentos\arribo` y escribe `conductor\android\key.properties`, que no se sube):

```bash
cd conductor; powershell -ExecutionPolicy Bypass -File .\crear-llave.ps1
```

**Guarde el `.jks` y su clave fuera del PC.** Si se pierden, un APK nuevo no se instala encima del
anterior: habría que desinstalar la app en cada celular.

Cada vez que haya que repartir la app (exige que el servidor ya responda):

```bash
cd conductor; powershell -ExecutionPolicy Bypass -File .\compilar-apk.ps1 -Servidor https://DOMINIO
```

Deja `conductor\build\arribo-conductor-<versión>.apk` y muestra su huella SHA-256. Para instalarlo:
por USB con `adb install -r` (ver `conductor/README.md`) o enviando el archivo al celular y
abriéndolo (Android pide permitir "instalar apps desconocidas" la primera vez). Si el celular tenía
la versión de desarrollo (firmada con otra llave), hay que desinstalarla antes.

## 5. Comprobar (lo que pide la tarea)

1. `https://DOMINIO/salud/` en el navegador responde `{"estado": "ok", "servicio": "arribo"}`.
2. `http://DOMINIO/` redirige solo a `https://`.
3. En el celular con el APK instalado, la pantalla de ingreso dice abajo `https://DOMINIO`, y el
   conductor entra con su celular y PIN y ve su lista.
4. Asignarle un servicio desde el panel: le llega el aviso push.

## Día a día

| Para | Comando (en `/opt/arribo/codigo/despliegue`) |
|---|---|
| Actualizar a lo último de `main` | `./desplegar.sh` |
| Ver si todo está arriba | `docker compose ps` |
| Ver el registro del panel | `docker compose logs --tail 100 web` |
| Ver alertas y push de cada minuto | `docker compose logs --tail 50 tareas` |
| Ver los respaldos | `ls -lh /opt/arribo/respaldos` |
| Cargar la demo (solo antes de tener datos reales) | `docker compose exec web python manage.py demo_cargar` |
| Quitar la demo | `docker compose exec web python manage.py demo_borrar` |

Restaurar un respaldo (borra la base actual; pendiente de ensayo con restauración probada, fase 3):

```bash
docker compose exec -T db pg_restore --clean --if-exists --no-owner -U arribo -d arribo < /opt/arribo/respaldos/arribo-AAAA-MM-DD.dump
```

## Lo que no cubre la fase 1a

- Copia de los respaldos y de las fotos fuera del servidor, y restauración probada (fase 3).
- Fotos en Cloudflare R2 (fase 1b).
- Correo de alertas.
