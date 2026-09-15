"""
auth.py - Autenticacao por senha do painel.

O painel expoe ordens de compra e venda, a carteira e as chaves da corretora.
Sem login, qualquer pessoa que alcance a porta opera na conta do usuario. Aqui
fica o minimo necessario para isso nao acontecer:

- senha guardada apenas como hash (werkzeug / PBKDF2), nunca em texto puro;
- sessao em cookie assinado, com chave secreta persistida em data/settings.json
  para que as sessoes sobrevivam a um restart do servico;
- bloqueio temporario por IP apos varias tentativas erradas, que e o que torna
  inviavel varrer senhas por forca bruta.

Enquanto nao houver senha definida, o painel NAO serve nada: responde a todas
as rotas com a instrucao de rodar `set_password.py`. Isso e deliberado --
falhar fechado. A alternativa (deixar a primeira visita definir a senha) daria
o painel a quem chegasse primeiro, e este servico esta exposto na rede.
"""

import functools
import secrets
import threading
import time

from flask import jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from webapp import store

SESSION_KEY = "autenticado"
SESSION_DAYS = 7

# Bloqueio por forca bruta
MAX_TENTATIVAS = 5
JANELA_SEGUNDOS = 900          # tentativas sao esquecidas depois de 15 min
BLOQUEIO_SEGUNDOS = 900        # e o IP fica de castigo por 15 min

_tentativas: dict[str, list[float]] = {}
_LOCK = threading.RLock()

# Rotas que precisam responder sem sessao, senao nao ha como fazer login.
ROTAS_LIVRES = {"login", "do_login", "static"}


# --------------------------------------------------------------------------- #
# Senha
# --------------------------------------------------------------------------- #
def definir_senha(senha: str):
    """Grava o hash da senha. A senha em si nunca toca o disco."""
    if len(senha) < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
    store.save_settings({"password_hash": generate_password_hash(senha)})


def senha_configurada() -> bool:
    return bool(store.load_settings().get("password_hash"))


def senha_confere(senha: str) -> bool:
    hash_salvo = store.load_settings().get("password_hash") or ""
    if not hash_salvo:
        return False
    return check_password_hash(hash_salvo, senha)


def chave_secreta() -> str:
    """
    Chave de assinatura dos cookies, criada uma vez e reaproveitada.

    Se fosse gerada a cada boot, todo restart do servico deslogaria o usuario.
    """
    settings = store.load_settings()
    chave = settings.get("secret_key")
    if not chave:
        chave = secrets.token_hex(32)
        store.save_settings({"secret_key": chave})
    return chave


# --------------------------------------------------------------------------- #
# Bloqueio por tentativas
# --------------------------------------------------------------------------- #
def _ip() -> str:
    return request.remote_addr or "desconhecido"


def bloqueado_ate(ip: str) -> float:
    """Momento (epoch) em que o IP volta a poder tentar; 0 se estiver liberado."""
    with _LOCK:
        recentes = [t for t in _tentativas.get(ip, []) if time.time() - t < JANELA_SEGUNDOS]
        _tentativas[ip] = recentes
        if len(recentes) >= MAX_TENTATIVAS:
            return recentes[-1] + BLOQUEIO_SEGUNDOS
    return 0.0


def registrar_falha(ip: str):
    with _LOCK:
        _tentativas.setdefault(ip, []).append(time.time())


def limpar_tentativas(ip: str):
    with _LOCK:
        _tentativas.pop(ip, None)


# --------------------------------------------------------------------------- #
# Guarda das rotas
# --------------------------------------------------------------------------- #
def _quer_json() -> bool:
    return request.path.startswith("/api/")


def registrar(app):
    """Liga a autenticacao no app Flask."""
    app.secret_key = chave_secreta()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,   # o cookie fica invisivel para JavaScript
        SESSION_COOKIE_SAMESITE="Lax",  # nao viaja em requisicoes de outros sites
        PERMANENT_SESSION_LIFETIME=SESSION_DAYS * 86400,
    )

    @app.before_request
    def exigir_login():
        if request.endpoint in ROTAS_LIVRES:
            return None

        if not senha_configurada():
            msg = ("Nenhuma senha definida. Na VPS, rode: "
                   "venv/bin/python set_password.py")
            if _quer_json():
                return jsonify({"ok": False, "error": msg}), 503
            return (f"<h1>Painel bloqueado</h1><p>{msg}</p>", 503,
                    {"Content-Type": "text/html; charset=utf-8"})

        if session.get(SESSION_KEY):
            return None

        if _quer_json():
            return jsonify({"ok": False, "error": "Sessao expirada.", "login": True}), 401
        return redirect(url_for("login", next=request.path))

    @app.route("/login", methods=["GET"])
    def login():
        if session.get(SESSION_KEY):
            return redirect("/")
        return render_template("login.html", erro=None,
                               configurada=senha_configurada())

    @app.route("/login", methods=["POST"])
    def do_login():
        ip = _ip()
        ate = bloqueado_ate(ip)
        if ate:
            faltam = int((ate - time.time()) / 60) + 1
            return render_template("login.html", configurada=True,
                                   erro=f"Muitas tentativas. Aguarde {faltam} min."), 429

        senha = request.form.get("senha", "")
        if senha_confere(senha):
            limpar_tentativas(ip)
            session.permanent = True
            session[SESSION_KEY] = True
            store.log_activity("info", f"Login no painel a partir de {ip}.")
            destino = request.form.get("next") or "/"
            # So aceita caminho interno: "next" vem do navegador e um valor como
            # "//site-externo" viraria um redirecionamento para fora.
            if not destino.startswith("/") or destino.startswith("//"):
                destino = "/"
            return redirect(destino)

        registrar_falha(ip)
        store.log_activity("warning", f"Tentativa de login incorreta a partir de {ip}.")
        return render_template("login.html", configurada=True,
                               erro="Senha incorreta."), 401

    @app.route("/logout", methods=["GET", "POST"])
    def logout():
        session.clear()
        return redirect(url_for("login"))
