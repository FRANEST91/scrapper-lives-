#!/usr/bin/env python3
"""
Publicador manual: envía todas las tarjetas pendientes al canal de Telegram.
Uso: python publisher_cli.py
"""
from publisher import publish_pending_cards, get_pending_count

if __name__ == "__main__":
    pendientes = get_pending_count()
    print(f"Tarjetas pendientes: {pendientes}")
    if pendientes > 0:
        enviadas = publish_pending_cards()
        print(f"Publicadas: {enviadas}/{pendientes}")
    else:
        print("Nada que publicar.")
