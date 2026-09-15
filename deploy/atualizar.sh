#!/usr/bin/env bash
#
# atualizar.sh - Atualiza a instalacao de producao do painel na VPS.
#
# Uso (na VPS, dentro da pasta do projeto):
#     bash deploy/atualizar.sh
#
# Detecta sozinho se o painel roda sob PM2 ou systemd. Para forcar o nome:
#     PM2_APP=meu-app     bash deploy/atualizar.sh
#     SERVICO=meu-servico bash deploy/atualizar.sh
#
# O cuidado principal deste script e com data/ e reports/. Ate esta
# atualizacao, a carteira simulada (data/paper_wallet.json), as metricas
# (data/backtests.json) e os relatorios (reports/*.png) estavam versionados no
# Git. O commit que voce esta puxando para de versiona-los -- o que significa
# que ESTE merge tenta apaga-los do disco. Como e o estado real de producao,
# fazemos copia antes e devolvemos depois. A partir do proximo pull eles ficam
# ignorados pelo Git e nada mais encosta neles.

set -euo pipefail

SERVICO="${SERVICO:-dqn-dashboard}"
PM2_APP="${PM2_APP:-dqn-dashboard}"
PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CARIMBO="$(date +%Y%m%d-%H%M%S)"
BACKUP="$PROJETO/backup-$CARIMBO"

cd "$PROJETO"
echo "==> Projeto: $PROJETO"

# --------------------------------------------------------------------------- #
# 1. Parar o servico
# --------------------------------------------------------------------------- #
GERENCIADOR="nenhum"

if command -v pm2 >/dev/null && pm2 jlist 2>/dev/null | grep -q "\"name\":\"${PM2_APP}\""; then
    GERENCIADOR="pm2"
    echo "==> Parando o app PM2 '$PM2_APP'..."
    pm2 stop "$PM2_APP"
elif command -v systemctl >/dev/null && systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICO}\.service"; then
    GERENCIADOR="systemd"
    echo "==> Parando o servico systemd '$SERVICO'..."
    sudo systemctl stop "$SERVICO"
else
    echo "!!! Nao achei o app PM2 '$PM2_APP' nem o servico systemd '$SERVICO'."
    if command -v pm2 >/dev/null; then
        echo "    Apps PM2 disponiveis:"
        pm2 list
        echo "    Rode de novo com: PM2_APP=<nome> bash deploy/atualizar.sh"
    fi
    echo "    Ou PARE o painel agora em outro terminal antes de continuar."
    read -r -p "    Pressione ENTER quando o painel estiver parado (Ctrl+C para abortar). "
fi

# --------------------------------------------------------------------------- #
# 2. Backup do estado de producao
# --------------------------------------------------------------------------- #
echo "==> Backup do estado em $BACKUP"
mkdir -p "$BACKUP"
[ -d data ]    && cp -a data    "$BACKUP/"
[ -d reports ] && cp -a reports "$BACKUP/"
[ -d models ]  && cp -a models  "$BACKUP/"
echo "    guardado: $(du -sh "$BACKUP" | cut -f1)"

# --------------------------------------------------------------------------- #
# 3. Puxar o codigo novo
# --------------------------------------------------------------------------- #
ANTES="$(git rev-parse --short HEAD)"
echo "==> Commit atual: $ANTES"

# Descarta as versoes RASTREADAS de data/ e reports/ para o merge nao travar.
# O conteudo real volta do backup no passo 4.
git checkout -- data reports 2>/dev/null || true

echo "==> git pull origin main"
git pull origin main

DEPOIS="$(git rev-parse --short HEAD)"
echo "==> Commit novo:  $DEPOIS"

# --------------------------------------------------------------------------- #
# 4. Devolver o estado de producao
# --------------------------------------------------------------------------- #
echo "==> Restaurando carteira, metricas e relatorios"
mkdir -p data reports
[ -d "$BACKUP/data" ]    && cp -a "$BACKUP/data/."    data/
[ -d "$BACKUP/reports" ] && cp -a "$BACKUP/reports/." reports/

if [ -f data/paper_wallet.json ]; then
    echo "    carteira restaurada ($(wc -c < data/paper_wallet.json) bytes)"
else
    echo "!!! data/paper_wallet.json nao existe; o painel vai criar uma carteira nova."
fi

# --------------------------------------------------------------------------- #
# 5. Dependencias (so se requirements.txt mudou)
# --------------------------------------------------------------------------- #
if ! git diff --quiet "$ANTES" "$DEPOIS" -- requirements.txt; then
    echo "==> requirements.txt mudou; instalando"
    if [ -x .venv/bin/pip ]; then
        .venv/bin/pip install -r requirements.txt
    else
        echo "!!! .venv/bin/pip nao encontrado. Instale na mao no seu ambiente Python."
    fi
else
    echo "==> requirements.txt sem mudancas; nada a instalar"
fi

# --------------------------------------------------------------------------- #
# 6. Religar
# --------------------------------------------------------------------------- #
case "$GERENCIADOR" in
    pm2)
        echo "==> Subindo o app PM2 '$PM2_APP'..."
        pm2 restart "$PM2_APP" --update-env
        sleep 5
        pm2 list
        ;;
    systemd)
        echo "==> Subindo o servico systemd '$SERVICO'..."
        sudo systemctl start "$SERVICO"
        sleep 5
        systemctl --no-pager --lines=5 status "$SERVICO" || true
        ;;
    *)
        echo "==> Suba o painel de novo do jeito que voce usa."
        read -r -p "    Pressione ENTER quando ele estiver no ar. "
        ;;
esac

# --------------------------------------------------------------------------- #
# 7. Conferir que a correcao entrou
# --------------------------------------------------------------------------- #
echo
echo "==> Verificando: cada ativo tem que ter um preco DIFERENTE."
echo "    (antes da correcao, todos vinham com o mesmo preco)"
sleep 5
curl -s -m 180 "http://127.0.0.1:8000/api/overview?refresh=1"   | python3 -c '
import datetime, json, sys

d = json.load(sys.stdin)
ativos = d.get("stocks", []) + d.get("crypto", [])
precos, cripto_hoje, hoje = [], [], datetime.date.today().strftime("%d/%m/%Y")

for a in ativos:
    s = a["signal"]
    if not s.get("available"):
        print("   %-10s INDISPONIVEL: %s" % (a["ticker"], str(s.get("message"))[:60]))
        continue
    print("   %-10s %-14s data=%s" % (a["ticker"], s.get("price"), s.get("quote_date")))
    precos.append(s.get("price"))
    if a["asset_class"] == "crypto":
        cripto_hoje.append(s.get("quote_date") == hoje)

print()
falhas = []

# 1. Dados cruzados: com o bug, threads paralelas devolviam a mesma serie.
if not precos:
    falhas.append("nenhum preco foi retornado")
elif len(set(precos)) != len(precos):
    falhas.append("ha precos REPETIDOS entre ativos (bug dos dados cruzados)")

# 2. Preco do dia: o `end` do Yahoo e exclusivo, e o codigo antigo passava a
#    data de hoje, descartando o candle de hoje. Cripto negocia 24/7, entao a
#    barra de hoje sempre existe -- e o teste mais direto de que o fix subiu.
if cripto_hoje and not any(cripto_hoje):
    falhas.append("nenhuma cripto tem cotacao de hoje (%s): o processo no ar "
                  "ainda usa o codigo antigo" % hoje)

if falhas:
    print("   ATENCAO: a correcao NAO parece estar no ar.")
    for f in falhas:
        print("     - " + f)
    print("   Confira se o processo que atende a porta 8000 foi reiniciado")
    print("   DEPOIS do git pull:  ss -ltnp | grep :8000")
    sys.exit(1)

print("   OK: precos distintos e cotacao do dia. A correcao esta no ar.")
' || echo "   (nao consegui consultar a API; confira os logs do servico)"

echo
echo "==> Pronto. Backup preservado em: $BACKUP"
if [ "$GERENCIADOR" = "pm2" ]; then
    echo "    Logs:  pm2 logs $PM2_APP --lines 50"
fi
echo "    Para desfazer tudo:"
echo "      git reset --hard $ANTES && cp -a $BACKUP/data/. data/ && cp -a $BACKUP/reports/. reports/"
