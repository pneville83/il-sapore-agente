# 🍕 Il Sapore — Agente de pedidos por WhatsApp

Agente conversacional que atiende, toma y cobra pedidos de un restaurante de pizzas
por WhatsApp, en varias sedes, con panel administrativo y conciliación automática de
pagos con tarjeta.

> Proyecto de portafolio de AI Engineering: agente ReAct con 23 herramientas,
> permisos por rol, pagos reales con Payphone y despliegue en producción.

- **Panel administrativo:** https://il-sapore.streamlit.app
- **API:** https://il-sapore-agente.onrender.com
- **Código:** https://github.com/pneville83/il-sapore-agente

## El problema

Un restaurante con varias sedes recibía los pedidos por WhatsApp de forma manual:
el cliente escribía, alguien leía, anotaba el pedido, calculaba el total, mandaba un
link de pago y después verificaba a mano si el pago había llegado. Con varios pedidos
al mismo tiempo se perdían mensajes y se cobraba tarde.

Este proyecto reemplaza ese proceso completo con un agente que conversa, cotiza, toma
el pedido, cobra y notifica al encargado de la sede, sin intervención humana en el
caso normal.

## Cómo funciona

    WhatsApp del cliente
            │
            ▼
    Bot Baileys (TV Box con Armbian)
            │  texto + historial
            ▼
    FastAPI en Render ──► Agente ReAct (DeepSeek) ──► 23 herramientas ──► Supabase
            │
            ├──► Payphone (link de pago)
            │
            └──► notificaciones_pendientes ──► el bot las envía cada 10 s

    cron-job.org ──► POST /payphone/procesar_pendientes ──► concilia pagos con tarjeta

1. El cliente escribe por WhatsApp. El bot le pasa el mensaje al agente junto con el
   historial de la conversación.
2. El agente identifica al cliente, consulta el menú y los precios de su sede, arma el
   pedido y decide el flujo según el método de pago.
3. Según el método:
   - **Efectivo:** se notifica al encargado de la sede de inmediato.
   - **Transferencia:** el cliente manda el comprobante, el bot lo reenvía al
     superadmin, que autoriza; recién entonces se notifica al encargado.
   - **Tarjeta:** se genera un link de Payphone; el pago se concilia automáticamente y,
     al confirmarse, se registra la transacción y se avisa al cliente y al encargado.
4. Las notificaciones se encolan en la base de datos y el bot las recoge cada 10
   segundos. Así el agente nunca depende de que el bot esté en línea.

## Funcionalidades

- **Pedidos por WhatsApp** con memoria de conversación (15 mensajes) y detección del
  número real del cliente, incluidos los identificadores LID de WhatsApp.
- **Tres métodos de pago** con flujos distintos y automatizados.
- **Conciliación activa de pagos** con Payphone: se consulta el estado real de cada
  transacción por `clientTransactionId`, sin depender de la notificación externa
  (Payphone la habilita por solicitud y tarda meses).
- **Idempotencia**: reintentar el procesamiento nunca duplica un pago.
- **23 herramientas** de inventario, ventas, gastos, compras, pagos, pedidos, clientes,
  administración y etapas de entrega.
- **Permisos por rol** (cliente, empleado, admin, superadmin) en dos capas: lista negra
  global y lista blanca por rol.
- **Multi-sede**: precios, costos y disponibilidad por ubicación; cada sede tiene su
  propio bot y su propio encargado.
- **Apertura y cierre del bot** por comando (`/abrir`, `/cerrar`), solo administradores.
- **Comprobantes de transferencia** reenviados al superadmin para autorización.
- **Panel administrativo** en Streamlit con login y consultas.
- **Detección de imágenes**: el bot distingue un comprobante de transferencia de una
  foto enviada por error; si el pago fue con tarjeta, no se pide comprobante.

## Stack

| Capa | Tecnología |
|---|---|
| Agente | DeepSeek API (formato OpenAI) + bucle ReAct propio |
| API | FastAPI + Uvicorn, Pydantic, SlowAPI |
| Base de datos | PostgreSQL en Supabase (RLS activo) |
| Bot de WhatsApp | Node.js + @whiskeysockets/baileys |
| Pagos | Payphone (API Link + consulta de estado) |
| Panel | Streamlit |
| Despliegue | Render (API), Streamlit Cloud (panel), TV Box con Armbian (bot), Docker Hub (imagen) |

## Estructura

    app/
    ├── main.py               # App FastAPI (CORS, rate limit, cabeceras)
    ├── core/
    │   ├── config.py         # Variables de entorno y validación
    │   ├── llm.py            # Cliente DeepSeek
    │   ├── auth.py           # Identificación y autenticación
    │   └── limiter.py        # Rate limiting
    ├── agent/
    │   ├── definitions.py    # Esquemas JSON de las 23 herramientas
    │   └── executor.py       # Bucle ReAct, prompts por rol, permisos
    ├── tools/                # Implementación de las herramientas
    │   ├── inventario.py  ventas.py  gastos.py  compras.py
    │   ├── pagos.py          # Payphone + registrar_pago
    │   ├── pedidos.py        # Pedidos, orquestación y notificaciones
    │   ├── clientes.py  admin.py
    │   └── payphone_procesador.py   # Conciliación y procesamiento de pagos
    └── api/
        └── routes.py         # Endpoints HTTP

    app_streamlit.py          # Panel administrativo

## Puesta en marcha local

    # 1. Dependencias
    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

    # 2. Variables de entorno
    cp .env.example .env             # y rellena los valores reales

    # 3. API
    uvicorn app.main:app --reload --port 8000

    # 4. Panel (en otra terminal)
    streamlit run app_streamlit.py

## Variables de entorno

Las claves están documentadas en `.env.example`:

- `DEEPSEEK_API_KEY` — LLM del agente.
- `DATABASE_URL` — cadena de conexión de Supabase (PostgreSQL).
- `PAYPHONE_*` — credenciales y endpoints de Payphone. `PAYPHONE_CHECK_STATUS_URL`
  es la base (`.../api/Sale/client`); el código le concatena el `clientTransactionId`.
- `SUPERADMIN_WHATSAPP` — número que autoriza transferencias.
- `CORS_ORIGINS` y `OPENAPI_URL` — seguridad por entorno.
- `CRON_SECRET` — protege el endpoint de conciliación.

## Endpoints principales

| Método | Ruta | Para qué |
|---|---|---|
| POST | `/preguntar` | Consulta al agente desde el panel |
| POST | `/login` | Login del panel |
| GET | `/health` | Health check (keep-alive) |
| POST | `/whatsapp` | Bot → agente (texto + historial) |
| POST | `/whatsapp/comprobante` | Bot → guarda comprobante de transferencia |
| GET | `/whatsapp/pendientes` | Bot → notificaciones por enviar |
| POST | `/whatsapp/pendientes/marcar` | Bot → marca notificaciones enviadas |
| GET | `/whatsapp/pedido_pendiente` | Bot → pedido pendiente de transferencia |
| GET | `/whatsapp/pedido_metodo` | Bot → método de pago de un pedido |
| POST/GET | `/bot/estado` | Abrir/cerrar el bot por sede |
| POST | `/payphone/procesar_pendientes` | Cron → concilia y procesa pagos |

## Seguridad

- RLS activo en Supabase.
- Rate limiting: 20 req/min para el agente y 5 req/min para login.
- CORS restringido a los orígenes de producción y desarrollo.
- Cabeceras HTTP de seguridad y validación con Pydantic.
- Documentación de la API desactivada en producción.
- Permisos de herramientas en dos capas, con inyección de rol desde el servidor: el LLM
  no puede falsificar el rol ni la sede.
- Confirmación obligatoria antes de acciones destructivas.
- `.env` fuera de Git y contenedor Docker sin privilegios.
- Endpoint de cron protegido con secreto en cabecera.

## Pruebas

Las pruebas son end-to-end sobre WhatsApp real, organizadas por rol:

- **Cliente:** efectivo, transferencia confiable y no confiable, tarjeta, cambio de
  método de pago, cancelación.
- **Admin:** reportes de su sede, disponibilidad de productos, permisos.
- **Superadmin:** reportes globales, autorización de transferencias, etapas de entrega,
  apertura y cierre del bot.

El flujo de tarjeta está verificado de punta a punta: pago, conciliación, registro de la
transacción y aviso al cliente y al encargado.

## Estado y siguientes pasos

- [x] Agente con 23 herramientas y permisos por rol
- [x] Bot de WhatsApp con historial y notificaciones
- [x] Tres métodos de pago, incluida la conciliación de tarjeta
- [x] Panel administrativo y despliegue en producción
- [ ] Pruebas unitarias
- [ ] Cancelación y modificación de pedidos por el cliente
- [ ] RAG sobre la información del negocio (pgvector)
- [ ] Notas de voz (Whisper)
- [ ] Video demo

## Autor

Peter Neville — https://github.com/pneville83