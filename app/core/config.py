import os
from dotenv import load_dotenv

load_dotenv()

# --- DeepSeek ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# --- Supabase ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Payphone ---
PAYPHONE_API_KEY = os.getenv("PAYPHONE_API_KEY")
PAYPHONE_STORE_ID = os.getenv("PAYPHONE_STORE_ID")
PAYPHONE_GENERATE_LINK_URL = os.getenv("PAYPHONE_GENERATE_LINK_URL")
PAYPHONE_RESPONSE_URL = os.getenv("PAYPHONE_RESPONSE_URL")
PAYPHONE_CHECK_STATUS_URL = os.getenv("PAYPHONE_CHECK_STATUS_URL")

# --- Hugging Face (opcional) ---
HF_TOKEN = os.getenv("HF_TOKEN", "")

# --- Validación de variables críticas ---
def validar_config():
    faltantes = []
    if not DEEPSEEK_API_KEY:
        faltantes.append("DEEPSEEK_API_KEY")
    if not DATABASE_URL:
        faltantes.append("DATABASE_URL")
    if not PAYPHONE_API_KEY:
        faltantes.append("PAYPHONE_API_KEY")
    if not PAYPHONE_STORE_ID:
        faltantes.append("PAYPHONE_STORE_ID")
    if not PAYPHONE_GENERATE_LINK_URL:
        faltantes.append("PAYPHONE_GENERATE_LINK_URL")
    if not PAYPHONE_RESPONSE_URL:
        faltantes.append("PAYPHONE_RESPONSE_URL")
    
    if faltantes:
        raise ValueError(f"Faltan variables de entorno: {', '.join(faltantes)}")
    
    print("✅ Configuración cargada correctamente.")