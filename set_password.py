"""
set_password.py - Define ou troca a senha de acesso ao painel.

Uso, na pasta do projeto:
    venv/bin/python set_password.py

A senha e pedida sem eco na tela e gravada apenas como hash em
data/settings.json, que nao vai para o Git. Nao ha como recuperar a senha
depois; para trocar, basta rodar este script de novo.
"""

import getpass
import sys

import src  # noqa: F401  (ajusta o encoding dos streams)

from webapp import auth, config, store


def main():
    config.ensure_dirs()
    ja_tem = auth.senha_configurada()

    print()
    print("=" * 52)
    print("   SENHA DE ACESSO AO PAINEL DO ROBO DE TRADING")
    print("=" * 52)
    print(f"   Estado atual: {'senha ja definida' if ja_tem else 'NENHUMA senha definida'}")
    print("=" * 52)
    print()

    try:
        senha = getpass.getpass("Nova senha (minimo 8 caracteres): ")
        confirmacao = getpass.getpass("Repita a senha: ")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado. Nada foi alterado.")
        return 1

    if senha != confirmacao:
        print("\n[-] As senhas nao conferem. Nada foi alterado.")
        return 1

    try:
        auth.definir_senha(senha)
    except ValueError as exc:
        print(f"\n[-] {exc} Nada foi alterado.")
        return 1

    store.log_activity("warning", "Senha de acesso ao painel alterada.")
    print()
    print("[+] Senha gravada (apenas o hash; a senha nao fica em disco).")
    print("    Reinicie o painel para aplicar:")
    print("        sudo systemctl restart dqn-dashboard")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
