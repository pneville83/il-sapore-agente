# prueba_cambiar_metodo.py
from app.tools.pedidos import crear_pedido, cambiar_metodo_pago_pedido

# 1. Crear un pedido en tarjeta
r1 = crear_pedido(
    whatsapp_cliente="593999999999",
    ubicacion_id=1,
    metodo_pago="tarjeta",
    items=[{"producto_id": 39, "variacion_id": None, "cantidad": 1}],
    nombre_cliente="Test Cambio",
    direccion_mz="9",
    direccion_villa="6",
    etapa="2",
)
print("Crear pedido:", r1)

if isinstance(r1, dict) and r1.get("estado") == "ok":
    pedido_id = r1["pedido_id"]
    print(f"Pedido creado: #{pedido_id}")

    # 2. Cambiar a efectivo
    r2 = cambiar_metodo_pago_pedido(pedido_id, "efectivo")
    print("Cambiar a efectivo:", r2)

    # 3. Intentar cambiar a un método inválido
    r3 = cambiar_metodo_pago_pedido(pedido_id, "bitcoin")
    print("Método inválido:", r3)