# Finance Tracker

Finanzas personales de un solo usuario: un bot de Telegram (`bot/`, Python) que
registra gastos y archiva documentos, y un dashboard (`web/`, Next.js 14 App
Router) que los muestra. Los dos hablan con la misma Supabase; no hay API entre
ellos. Código, comentarios, commits y tests van en español.

El README cubre deploy, variables de entorno y proveedores de LLM. Acá va lo que
hace falta para tocar el código sin releerlo.

## Comandos

```bash
# Tests del bot (desde la raíz; sin PYTHONPATH no encuentra el paquete `bot`)
PYTHONPATH=. bot/.venv/bin/python -m pytest bot/tests -q

# Web
cd web && npx tsc --noEmit      # type-check
cd web && npm run dev           # apunta a la Supabase de PRODUCCIÓN
```

No hay base de desarrollo: `bot/.env` y `web/.env.local` apuntan a producción.
Cualquier script que escriba, primero en modo solo-lectura y mostrando qué
cambiaría.

## Deploy

- Web: Vercel deploya solo con cada push a `main`.
- Bot: systemd en un servidor Oracle, con `deploy-bot` (alias del usuario). Un
  cambio en `bot/` no corre en producción hasta ese deploy.

## Mapa

| Dónde | Qué |
|---|---|
| `bot/main.py` | Handlers de Telegram. Solo procesa documentos (PDF, imagen o foto) y los botones de recurrentes; no hay chat. |
| `bot/gmail_poller.py` | Mails de bancos y tarjetas → gastos (regex primero, LLM de respaldo). |
| `bot/facturas_poller.py` | Mails de aviso de factura → fila en `facturas` + PDF a Drive cuando se puede bajar. |
| `bot/tools/documentos.py` | Identifica un documento suelto: servicio, tipo (factura/comprobante), monto y fecha. De una imagen o un PDF escaneado el modelo de visión solo transcribe el texto; la identificación es la misma. |
| `bot/tools/conciliacion.py` | Elige a qué factura pendiente corresponde un documento. |
| `bot/tools/archivado.py` | Orquesta: Drive + fila en `archivos_drive` + gasto + saldar la factura. |
| `bot/tools/estado.py` | Lo que tiene que sobrevivir a un reinicio (tabla `bot_estado`): marca del recordatorio diario, salud de cada poller y mails sin procesar. La web lo lee para la bandeja del Panel. |
| `bot/db/queries.py` | Todo el acceso a Supabase del bot. |
| `web/src/lib/queries.ts` | Todo el acceso de lectura de la web. Lo que puede pasar de 1000 filas va por `traerTodo` (Supabase corta ahí sin avisar). |
| `web/src/lib/fechas.ts` | "Hoy" en hora argentina. En código de servidor nunca `new Date()` para saber el día o el mes: Vercel corre en UTC. |
| `web/src/lib/nav.ts` | Las cinco secciones del menú y las pestañas de cada una. |
| `web/src/app/*/actions.ts` | Server actions (escrituras). |
| `supabase/migrations/` | Esquema, numerado. Se aplican a mano. |

## Modelo de facturas y archivos

Es la parte que más bugs dio; conviene tenerla clara antes de tocarla.

- `servicios`: los seis fijos (edenor, metrogas, aysa, aysa_baulera, personal,
  consorcio_gallo), cada uno atado a un `gastos_recurrentes`.
- Un mail de aviso puede traer varias facturas (AySA manda todas las cuentas
  del titular juntas): el parser devuelve una por fila y la idempotencia es por
  (mail, servicio). Si la factura trae identificador, una cuenta sin registrar
  se rechaza; el slug solo rutea lo que no trae número (expensas).
- `facturas`: una por servicio y vencimiento. `estado` pendiente → pagada, y al
  pagarse guarda el `gasto_id` del pago. La crea el poller de mails.
- `archivos_drive`: un PDF en Drive, con DOS vínculos opcionales e
  independientes:
  - `gasto_id` — es lo que mira la tab **Comprobantes** ("Vinculado").
  - `factura_id` — es lo que mira la tab **Registro** (la celda está completa
    si la factura está paga y tiene un archivo tipo `factura` y uno
    `comprobante`).

  Un archivo de un servicio fijo tiene que terminar con los dos. Quien escriba
  uno debe ocuparse del otro: al saldar una factura se propaga el gasto a sus
  archivos, y al vincular a mano un gasto que saldó una factura se cuelga
  también de ella.

- El ruteo de un documento es siempre por identificador numérico (cuenta,
  cliente, CBU) buscado en el texto del PDF, nunca por nombre ni dirección.
- Un documento nunca se descarta: si no se le encuentra factura se archiva
  huérfano y se avisa.
- El orden de llegada no está garantizado. El usuario puede mandar el
  comprobante antes que la factura, y el PDF puede llegar antes o después del
  mail de aviso.

### Particularidades por servicio

- **MetroGAS**: el PDF no se puede bajar solo (reCAPTCHA validado en servidor;
  ver el commit `5ccd85f`), así que la factura siempre la manda el usuario por
  Telegram. Además el vencimiento no se lee del PDF: sale la fecha de emisión.
  Por eso una factura tardía se ubica por importe exacto y no por fecha.
- **Edenor**: también escribe el vencimiento pegado al texto.
- **AySA Baulera**: cuenta aparte (1932903, U.C. 074) que llega en el mismo
  mail que el depto. Factura semestral por adelantado, recurrente `semestral`.
  Cada PDF se empareja con su factura por el N° de LSP, no por el orden de los
  botones.
- **Personal Pay**: sus comprobantes pierden los centavos al extraerse. El monto
  del gasto sale siempre de la factura, no del comprobante.
- **Consorcio Gallo**: no tiene número de cuenta en el mail (el remitente es el
  identificador) y tiene un paso extra, el borrador de mail a la administración.

## Convenciones

- El bot no guarda en memoria nada que importe después de un reinicio (cada
  `deploy-bot` lo reinicia). Va a `bot_estado`, o viaja completo en el
  `callback_data` del botón.

- Los fixes llevan un test que reproduce el caso real, con un docstring que
  cuenta el bug ("Bug real: ..."). Los tests unitarios mockean Drive y la base
  (ver la clase `Entorno` en `bot/tests/test_archivado.py`).
- Ante la duda no se escribe ni se adivina: se pregunta o se avisa. Un dato
  faltante se arregla; uno incorrecto contamina el histórico.
- `emails/`, `facturas/` y `comprobantes/` en la raíz son documentos reales de
  referencia, ignorados por git. Sirven para probar un parser contra el PDF
  verdadero.
