# Finance Tracker

Bot de Telegram + web app para seguimiento de finanzas personales.

El proceso del bot (`finance-bot`) hace dos cosas: atiende Telegram y corre los
pollers de Gmail que auto-registran los gastos. Aunque no se use el chat, el
servicio tiene que estar corriendo.

---

## Dependencias del servidor

El bot corre con systemd sobre el venv, sin Docker. Además de `bot/requirements.txt`
hace falta un paquete de sistema:

```bash
sudo apt install poppler-utils   # lo necesita pdf2image para el fallback visión del parser BBVA
```

---

## Variables de entorno del LLM

Las tareas automáticas (parseo de emails bancarios, categorización, matching de
recurrentes) usan proveedores con free tier amplio, en cadena. Alcanza con
configurar uno, pero con los dos hay redundancia gratis:

```bash
GROQ_API_KEY=...        # primario   — https://console.groq.com
CEREBRAS_API_KEY=...    # secundario — https://cloud.cerebras.ai
```

Opcionalmente `GROQ_MODEL` / `CEREBRAS_MODEL` para pisar los modelos por defecto.

No hay ninguna dependencia de la API de Gemini: su free tier quedó en ~5
requests/día y el fallback pasó a exigir prepago. `GOOGLE_API_KEY` y
`GOOGLE_API_KEY_PAID` ya no se usan y se pueden borrar del `.env`.

⚠️ Las credenciales de **Gmail** (`GMAIL_*`) y **Drive** (`DRIVE_*`,
`GOOGLE_DRIVE_ROOT_FOLDER_ID`) son otra cosa: son OAuth de Workspace, no de IA.
Sin ellas no hay emails que leer ni dónde archivar. No tocarlas.

Para verificar que las keys andan y que los modelos configurados existen:

```bash
python -m bot.llm_client
```

---

## Día a día

### Conectarse al servidor

```bash
oracle
```

---

### Deployar cambios en el bot

```bash
deploy-bot
```

### Sincronizar .env local al servidor

```bash
sync-env
```

Copia `bot/.env` local al servidor y reinicia el bot automáticamente.

---

### Ver logs

```bash
# En el servidor — logs en vivo
sudo journalctl -u finance-bot -f

# Últimas 100 líneas
sudo journalctl -u finance-bot -n 100

# Logs de hoy
sudo journalctl -u finance-bot --since today
```

---

### Comandos del servicio

```bash
sudo systemctl status finance-bot    # ver estado
sudo systemctl restart finance-bot   # reiniciar
sudo systemctl stop finance-bot      # parar
sudo systemctl start finance-bot     # iniciar
```

---

### Deployar cambios en la web

La web se deploya automáticamente en Vercel al hacer push a `main`.

```bash
git push  # Vercel detecta los cambios y deploya solo
```
