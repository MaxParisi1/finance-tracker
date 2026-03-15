# Deploy del bot a Fly.io

## Prerequisitos

```bash
# Instalar Fly CLI (si no lo tenés)
brew install flyctl

# Login (una sola vez)
fly auth login
```

---

## Deploy de cambios

Desde la raíz del proyecto (`finance-tracker/`):

```bash
fly deploy
```

Fly detecta el `fly.toml` en la raíz, construye la imagen Docker desde `bot/Dockerfile` y la deploya.

Para ver el progreso en tiempo real:

```bash
fly deploy --verbose
```

---

## Ver logs

```bash
# Logs en tiempo real
fly logs

# Logs de las últimas horas
fly logs --no-tail
```

---

## Gestionar secrets (variables de entorno)

```bash
# Ver qué secrets están seteados (solo los nombres, no los valores)
fly secrets list

# Agregar o actualizar un secret (redeploya automáticamente)
fly secrets set NOMBRE_VARIABLE=valor

# Agregar varios a la vez
fly secrets set VAR1=valor1 VAR2=valor2 VAR3=valor3

# Eliminar un secret
fly secrets unset NOMBRE_VARIABLE
```

Secrets actuales del bot:
- `TELEGRAM_BOT_TOKEN`
- `ALLOWED_TELEGRAM_USER_ID`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GOOGLE_API_KEY`
- `GMAIL_REFRESH_TOKEN`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`

---

## Estado y máquinas

```bash
# Ver estado general de la app
fly status

# Ver máquinas corriendo
fly machine list

# Reiniciar la app
fly apps restart finance-bot-max
```

---

## Renovar credenciales de Gmail

Si el refresh token de Gmail expira (poco frecuente, pero puede pasar):

```bash
# 1. Correr el script de auth localmente
cd /ruta/al/proyecto
python -m bot.auth_gmail

# 2. Actualizar el secret en Fly.io con el nuevo token
fly secrets set GMAIL_REFRESH_TOKEN=nuevo_token
# (fly redeploya automáticamente al setear un secret)
```

---

## Workflow típico de un cambio

```bash
# 1. Hacer los cambios en el código

# 2. Probar localmente si querés
cd bot
source .venv/bin/activate
python -m bot.main

# 3. Deploy
cd ..  # volver a la raíz del proyecto
fly deploy

# 4. Verificar que levantó bien
fly logs
```
