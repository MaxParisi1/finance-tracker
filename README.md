# Finance Tracker

Bot de Telegram + web app para seguimiento de finanzas personales.

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
