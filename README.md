# ============================================
# LLM (DeepSeek)
# ============================================
DEEPSEEK_API_KEY=sk-...

# ============================================
# BASE DE DATOS (Supabase)
# ============================================
DATABASE_URL=postgresql://postgres:password@db.xxx.supabase.co:5432/postgres
DB_SUPABASE=https://xxx.supabase.co

# ============================================
# HUGGING FACE (opcional, Fase 2)
# ============================================
HF_TOKEN=

# ============================================
# PAYPHONE
# ============================================
PAYPHONE_API_KEY=...
PAYPHONE_STORE_ID=...
PAYPHONE_CLIENT_ID=...
PAYPHONE_GENERATE_LINK_URL=https://pay.payphonetodoesposible.com/api/Links
PAYPHONE_CHECK_STATUS_URL=https://pay.payphonetodoesposible.com/api/button/V2/Confirm
PAYPHONE_RESPONSE_URL=https://tu-dominio.com/payphone/response
PAYPHONE_CANCELLATION_URL=https://tu-dominio.com/payphone/cancel

# ============================================
# SUPERADMIN
# ============================================
SUPERADMIN_WHATSAPP=593995293871

# ============================================
# ENTORNO / PRODUCCIÓN
# ============================================
# En local:
CORS_ORIGINS=http://localhost:8501
OPENAPI_URL=/openapi.json

# En Render (producción):
# CORS_ORIGINS=https://tu-app.streamlit.app,https://tu-servicio.onrender.com
# OPENAPI_URL=