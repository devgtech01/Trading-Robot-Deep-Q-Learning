"""
dashboard.py - Sobe o painel web interativo do Robô de Trading DQN.

Uso:
    python dashboard.py                  # http://127.0.0.1:8000
    python dashboard.py --port 8080
    python dashboard.py --host 0.0.0.0   # acessível na rede local
    python dashboard.py --no-browser
"""

import argparse
import threading
import webbrowser

from webapp import automation
from webapp.server import create_app


def main():
    parser = argparse.ArgumentParser(description="Painel Web do Robô de Trading DQN (Ações B3 + Cripto)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Endereço de escuta (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Porta HTTP (padrão: 8000)")
    parser.add_argument("--debug", action="store_true", help="Modo debug do Flask (recarrega ao salvar arquivos)")
    parser.add_argument("--no-browser", action="store_true", help="Não abrir o navegador automaticamente")

    args = parser.parse_args()
    app = create_app()

    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print("\n" + "=" * 60)
    print("      PAINEL DO ROBÔ DE TRADING DQN")
    print("=" * 60)
    print(f"  Interface:   {url}")
    print(f"  Agendador:   {'ativo' if automation.status()['scheduler_running'] else 'parado'}")
    print("  Encerrar:    Ctrl+C")
    print("=" * 60 + "\n")

    if not args.no_browser and not args.debug:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=args.debug, threaded=True)
    finally:
        automation.stop()


if __name__ == "__main__":
    main()
