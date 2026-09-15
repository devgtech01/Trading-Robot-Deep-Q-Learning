# Deploy na VPS (Fedora 42)

Caminho do fluxo: **seu computador → GitHub → VPS**. O código sobe por `git push`
daqui e desce por `git pull` lá. Estado de execução (carteira simulada, chaves,
log de atividade, relatórios) **não** trafega pelo Git: cada máquina tem o seu.

---

## ⚠️ Antes de tudo: o painel não tem senha

Não existe login, e as chaves da Binance ficam em texto puro em
`data/settings.json`. Se você publicar a porta 8000 no IP da VPS, qualquer um que
achar o endereço opera na sua conta. Por isso o serviço escuta apenas em
`127.0.0.1`.

Escolha **uma** forma de acesso:

- **Túnel SSH (recomendado, zero configuração).** No seu computador:
  ```bash
  ssh -L 8000:127.0.0.1:8000 usuario@IP_DA_VPS
  ```
  Com a sessão aberta, acesse `http://127.0.0.1:8000` no navegador local.
- **Proxy reverso** (nginx/Caddy) com HTTPS e autenticação básica, se precisar
  acessar de fora sem SSH.

Nunca libere a porta 8000 no `firewall-cmd`.

---

## 1. Preparar a VPS

```bash
sudo dnf install -y git python3.11 python3-pip
sudo useradd -r -m -d /opt/trading-robot -s /bin/bash trading
sudo -u trading -i
```

## 2. Clonar o projeto

```bash
git clone https://github.com/devgtech01/Trading-Robot-Deep-Q-Learning.git /opt/trading-robot
cd /opt/trading-robot
```

## 3. Ambiente virtual e dependências

Instale o **PyTorch de CPU primeiro**. O `pip install torch` padrão baixa a
versão com CUDA e arrasta ~2,5 GB de bibliotecas da NVIDIA que uma VPS sem placa
de vídeo nunca vai usar:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

O `MetaTrader5` é pulado automaticamente no Linux (marcador `sys_platform` no
`requirements.txt`) — veja a limitação na seção 7.

## 4. Testar na mão antes de virar serviço

```bash
python dashboard.py --host 127.0.0.1 --port 8000 --no-browser
```

Em outro terminal da VPS:

```bash
curl -s localhost:8000/api/overview | head -c 300
```

Tem que responder `{"ok":true,...}` com preços diferentes para cada ativo.
Encerre com `Ctrl+C`.

## 5. Subir como serviço

```bash
exit                                   # volta ao seu usuário com sudo
sudo cp /opt/trading-robot/deploy/dqn-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dqn-dashboard
systemctl status dqn-dashboard
journalctl -u dqn-dashboard -f         # acompanhar os logs
```

Se o SELinux reclamar (`avc: denied` no journal), confirme que o projeto está sob
`/opt` e que os arquivos pertencem ao usuário `trading`:

```bash
sudo chown -R trading:trading /opt/trading-robot
```

## 6. Configurar e começar os testes

Com o túnel SSH aberto, em `http://127.0.0.1:8000`:

1. **Configurações** → cole as chaves da [Binance Testnet](https://testnet.binance.vision/).
2. **Carteira** → *Reiniciar* as contas BRL e USDT (a VPS começa do zero mesmo).
3. Em cada ativo, escolha o modo (`Carteira simulada` ou `Binance Testnet`),
   defina o intervalo e ligue a automação.
4. Ligue a **chave-geral** da automação.
5. Deixe a trava de **dinheiro real desligada**.

## 7. O que muda em relação ao Windows

| Recurso | Windows | VPS Fedora |
|---|---|---|
| Carteira simulada (ações e cripto) | ✅ | ✅ |
| Binance Testnet / real | ✅ | ✅ |
| Treino e backtest | ✅ | ✅ (mais lento, CPU) |
| **MetaTrader 5** | ✅ | ❌ **não existe para Linux** |

A biblioteca `MetaTrader5` é só para Windows. Na VPS o modo `mt5` aparece na
interface mas recusa qualquer ordem com *"Biblioteca MetaTrader5 não instalada"* —
falha segura, não quebra o painel. Para operar ações de verdade via MT5 você
precisa de uma máquina Windows. Na VPS, ações só funcionam em **carteira
simulada**, que é exatamente o objetivo desta fase de testes.

## 8. Atualizar depois de novas mudanças

No seu computador:

```bash
git add -A && git commit -m "descrição" && git push
```

Na VPS:

```bash
sudo systemctl stop dqn-dashboard
sudo -u trading git -C /opt/trading-robot pull
sudo -u trading /opt/trading-robot/.venv/bin/pip install -r /opt/trading-robot/requirements.txt
sudo systemctl start dqn-dashboard
```

Se você **retreinar modelos na VPS**, os arquivos em `models/*.pt` ficam
diferentes do repositório e o `pull` reclama. Para descartar os da VPS e ficar
com os do GitHub:

```bash
sudo -u trading git -C /opt/trading-robot checkout -- models/
```

## 9. Fuso horário

O agendador usa a hora local da máquina, e a B3 opera em horário de Brasília. O
serviço já define `TZ=America/Sao_Paulo`. Para alinhar a VPS inteira:

```bash
sudo timedatectl set-timezone America/Sao_Paulo
```
