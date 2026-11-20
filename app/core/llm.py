from openai import OpenAI
from app.core.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

def llamar_llm(mensajes, herramientas=None):
    """
    Envía una lista de mensajes al LLM.
    No maneja historial: el agente es quien construye y mantiene el historial.
    """
    if herramientas:
        respuesta = client.chat.completions.create(
            model="deepseek-chat",
            messages=mensajes,
            tools=herramientas,
            tool_choice="auto"
        )
    else:
        respuesta = client.chat.completions.create(
            model="deepseek-chat",
            messages=mensajes
        )
    
    return respuesta.choices[0].message