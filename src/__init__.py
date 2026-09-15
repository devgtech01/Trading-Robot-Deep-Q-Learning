"""
src - Núcleo do Robô de Trading DQN (dados, ambiente de simulação, agente e execução).
"""

import sys


def enable_utf8_console():
    """
    Faz o console do Windows aceitar acentos.

    O terminal do Windows abre em cp1252 e os textos do robô ("Cotação", "Ação da
    IA", "Patrimônio") saem ilegíveis. Reconfigurar os streams para UTF-8 resolve
    sem exigir `chcp 65001` do usuário. Em terminais que não suportam a troca, o
    erro é ignorado e a saída segue como estava.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


enable_utf8_console()
