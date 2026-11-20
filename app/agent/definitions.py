from app.tools.inventario import consultar_inventario, buscar_producto_por_nombre
from app.tools.ventas import consultar_ventas_dia, consultar_flujo_dinero
from app.tools.gastos import registrar_gasto, consultar_gastos
from app.tools.compras import registrar_compra, consultar_compras
from app.tools.pagos import (
    generar_link_pago,
    registrar_pago,
    consultar_bancos,
    crear_transferencia_pendiente,
    autorizar_transferencia
)
from app.tools.admin import (
    solicitar_borrar_producto,
    solicitar_actualizar_precio,
    confirmar_accion,
    consultar_acciones_pendientes
)
from app.tools.clientes import buscar_o_crear_cliente
from app.tools.pedidos import (
    crear_pedido,
    deshabilitar_etapa,
    habilitar_etapa,
)

herramientas = [
    {
        "type": "function",
        "function": {
            "name": "buscar_producto_por_nombre",
            "description": "Busca un producto por su nombre (coincidencia parcial). Devuelve la lista de productos que coinciden.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre (o parte del nombre) del producto"}
                },
                "required": ["nombre"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_flujo_dinero",
            "description": "Devuelve el flujo de dinero: ventas, gastos y saldo por método de pago (efectivo, transferencia, tarjeta).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"},
                    "fecha_inicio": {"type": "string", "description": "Fecha de inicio (YYYY-MM-DD, opcional)"},
                    "fecha_fin": {"type": "string", "description": "Fecha de fin (YYYY-MM-DD, opcional)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_inventario",
            "description": "Devuelve la lista de productos disponibles con sus variaciones, precios y costos para una ubicación (sucursal).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_ventas_dia",
            "description": "Devuelve las ventas del día, el costo total y la ganancia bruta para una ubicación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"},
                    "fecha": {"type": "string", "description": "Fecha en formato YYYY-MM-DD (opcional, por defecto hoy)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_gasto",
            "description": "Registra un gasto del negocio o personal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string", "description": "Descripción del gasto"},
                    "monto": {"type": "number", "description": "Monto del gasto"},
                    "tipo": {"type": "string", "enum": ["negocio", "personal"], "description": "Tipo de gasto"},
                    "metodo_pago": {"type": "string", "enum": ["efectivo", "transferencia", "tarjeta"], "description": "Método de pago (obligatorio)"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"}
                },
                "required": ["descripcion", "monto", "tipo", "metodo_pago"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_gastos",
            "description": "Consulta los gastos de una ubicación, opcionalmente filtrados por tipo o rango de fechas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"},
                    "tipo": {"type": "string", "enum": ["negocio", "personal"], "description": "Filtrar por tipo (opcional)"},
                    "fecha_inicio": {"type": "string", "description": "Fecha de inicio (YYYY-MM-DD, opcional)"},
                    "fecha_fin": {"type": "string", "description": "Fecha de fin (YYYY-MM-DD, opcional)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_compra",
            "description": "Registra una compra de ingredientes o insumos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proveedor": {"type": "string", "description": "Nombre del proveedor"},
                    "descripcion": {"type": "string", "description": "Descripción de la compra"},
                    "monto": {"type": "number", "description": "Monto de la compra"},
                    "tipo": {"type": "string", "enum": ["negocio", "personal"], "description": "Tipo de compra"},
                    "metodo_pago": {"type": "string", "enum": ["efectivo", "transferencia", "tarjeta"], "description": "Método de pago (obligatorio)"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"}
                },
                "required": ["proveedor", "descripcion", "monto", "tipo", "metodo_pago"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_compras",
            "description": "Consulta las compras de una ubicación, opcionalmente filtradas por tipo o rango de fechas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"},
                    "tipo": {"type": "string", "enum": ["negocio", "personal"], "description": "Filtrar por tipo (opcional)"},
                    "fecha_inicio": {"type": "string", "description": "Fecha de inicio (YYYY-MM-DD, opcional)"},
                    "fecha_fin": {"type": "string", "description": "Fecha de fin (YYYY-MM-DD, opcional)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generar_link_pago",
            "description": "Genera un link de pago con Payphone para que el cliente pague con tarjeta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monto": {"type": "number", "description": "Monto a pagar en dólares"},
                    "client_transaction_id": {"type": "string", "description": "ID único de la transacción (máx 15 caracteres)"},
                    "referencia": {"type": "string", "description": "Descripción del pedido"}
                },
                "required": ["monto", "client_transaction_id", "referencia"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_pago",
            "description": "Registra un pago (efectivo, transferencia o tarjeta) en la base de datos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pedido_id": {"type": "integer", "description": "ID del pedido"},
                    "metodo": {"type": "string", "enum": ["efectivo", "transferencia", "tarjeta"], "description": "Método de pago"},
                    "monto": {"type": "number", "description": "Monto del pago"},
                    "banco_id": {"type": "integer", "description": "ID del banco (solo para transferencias)"},
                    "autorizacion": {"type": "string", "description": "Código de autorización (solo para transferencias)"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"}
                },
                "required": ["pedido_id", "metodo", "monto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_bancos",
            "description": "Devuelve la lista de bancos disponibles.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_transferencia_pendiente",
            "description": "Guarda una transferencia pendiente de autorización (cuando el cliente envía el comprobante).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pedido_id": {"type": "integer", "description": "ID del pedido"},
                    "cliente_whatsapp": {"type": "string", "description": "WhatsApp del cliente"},
                    "cliente_nombre": {"type": "string", "description": "Nombre del cliente"},
                    "media_base64": {"type": "string", "description": "Foto del comprobante en base64"},
                    "monto": {"type": "number", "description": "Monto de la transferencia"},
                    "banco_id": {"type": "integer", "description": "ID del banco"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"}
                },
                "required": ["pedido_id", "cliente_whatsapp", "cliente_nombre", "media_base64", "monto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "autorizar_transferencia",
            "description": "Autoriza o rechaza una transferencia pendiente. Si se autoriza, registra el pago.",
            "parameters": {
                "type": "object",
                "properties": {
                    "temp_id": {"type": "string", "description": "ID de la transferencia pendiente"},
                    "autorizado": {"type": "boolean", "description": "True para autorizar, False para rechazar"},
                    "autorizacion": {"type": "string", "description": "Código de autorización (opcional)"}
                },
                "required": ["temp_id", "autorizado"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "solicitar_borrar_producto",
            "description": "Solicita borrar un producto. NO lo borra directamente: crea una acción pendiente que el admin debe confirmar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_id": {"type": "integer", "description": "ID del producto a borrar"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"}
                },
                "required": ["producto_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "solicitar_actualizar_precio",
            "description": "Solicita actualizar el precio de un producto. NO lo actualiza directamente: crea una acción pendiente que el admin debe confirmar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_id": {"type": "integer", "description": "ID del producto"},
                    "nuevo_precio": {"type": "number", "description": "Nuevo precio"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (por defecto 1)"}
                },
                "required": ["producto_id", "nuevo_precio"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "confirmar_accion",
            "description": "Confirma o cancela una acción pendiente (borrar producto, actualizar precio).",
            "parameters": {
                "type": "object",
                "properties": {
                    "accion_id": {"type": "integer", "description": "ID de la acción pendiente"},
                    "confirmado": {"type": "boolean", "description": "True para confirmar, False para cancelar"}
                },
                "required": ["accion_id", "confirmado"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_acciones_pendientes",
            "description": "Devuelve la lista de acciones pendientes de confirmación.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_o_crear_cliente",
            "description": "Busca un cliente por su WhatsApp o LID. Si existe, devuelve su ficha (incluye si es confiable y qué datos le faltan). Si no existe y vienen todos los datos (nombre, Mz, Villa, Etapa), lo crea con confiable=TRUE. Si falta algún dato, devuelve la lista de campos_faltantes para que se los pidas al cliente. SIEMPRE úsala antes de crear_pedido para saber si necesitas pedir datos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "whatsapp": {"type": "string", "description": "WhatsApp del cliente (con código de país, sin +)"},
                    "whatsapp_lid": {"type": "string", "description": "LID de WhatsApp (opcional)"},
                    "nombre": {"type": "string", "description": "Nombre del cliente (solo si es nuevo)"},
                    "direccion_mz": {"type": "string", "description": "Mz de la dirección (solo si es nuevo)"},
                    "direccion_villa": {"type": "string", "description": "Villa de la dirección (solo si es nuevo)"},
                    "etapa": {"type": "string", "description": "Etapa de la dirección (solo si es nuevo)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crear_pedido",
            "description": "Crea un pedido en la base de datos. Calcula el total desde precios_ubicacion (NUNCA envíes precios). NO notifica al admin ni genera link de pago: eso lo hace el sistema después según metodo_pago. Verifica que la etapa esté habilitada. Si devuelve estado='faltan_datos_cliente', pide esos datos al cliente y vuelve a llamar. Si devuelve estado='etapa_no_habilitada', discúlpate con el cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "whatsapp_cliente": {"type": "string", "description": "WhatsApp del cliente"},
                    "whatsapp_lid": {"type": "string", "description": "LID del cliente (opcional)"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (1 por defecto)"},
                    "metodo_pago": {"type": "string", "enum": ["efectivo", "transferencia", "tarjeta"], "description": "Método de pago del pedido"},
                    "items": {
                        "type": "array",
                        "description": "Lista de items del pedido",
                        "items": {
                            "type": "object",
                            "properties": {
                                "producto_id": {"type": "integer", "description": "ID del producto (si no tiene variante)"},
                                "variacion_id": {"type": "integer", "description": "ID de la variación (si el producto tiene tamaño, etc.)"},
                                "cantidad": {"type": "integer", "description": "Cantidad (>0)"}
                            },
                            "required": ["cantidad"]
                        }
                    },
                    "nombre_cliente": {"type": "string", "description": "Nombre del cliente (si es nuevo)"},
                    "direccion_mz": {"type": "string", "description": "Mz (si es nuevo o cambió)"},
                    "direccion_villa": {"type": "string", "description": "Villa (si es nuevo o cambió)"},
                    "etapa": {"type": "string", "description": "Etapa de entrega"},
                    "observaciones": {"type": "string", "description": "Notas del cliente (ej: 'sin cebolla', 'sin salsas')"}
                },
                "required": ["whatsapp_cliente", "ubicacion_id", "metodo_pago", "items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deshabilitar_etapa",
            "description": "Deshabilita el despacho a una etapa para una ubicación. A partir de ahora, crear_pedido rechazará pedidos a esa etapa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "etapa": {"type": "string", "description": "Nombre de la etapa (ej: 'Guillermo')"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (1 por defecto)"}
                },
                "required": ["etapa"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "habilitar_etapa",
            "description": "Vuelve a habilitar el despacho a una etapa para una ubicación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "etapa": {"type": "string", "description": "Nombre de la etapa"},
                    "ubicacion_id": {"type": "integer", "description": "ID de la sucursal (1 por defecto)"}
                },
                "required": ["etapa"]
            }
        }
    },
]