# 🤖 Trading Robot Deep Q-Learning (B3 & Binance)

Sistema quantitativo autônomo de **Swing Trade** e **Criptomoedas (24/7)** baseado em **Aprendizado por Reforço Profundo (Deep Q-Learning / PyTorch)** com integração direta e automatizada para **MetaTrader 5 (XP Investimentos)** e **Binance (API Spot)**.

---

## 📋 Índice
1. [Instalação e Pré-requisitos](#-1-instalação-e-pré-requisitos)
2. [Configuração do MetaTrader 5 (XP Investimentos / B3)](#-2-configuração-do-metatrader-5-xp-investimentos--b3)
3. [Configuração da Binance (Criptomoedas 24/7)](#-3-configuração-da-binance-criptomoedas-247)
4. [Como Treinar os Modelos de IA](#-4-como-treinar-os-modelos-de-ia)
5. [Como Executar no Dia a Dia](#-5-como-executar-no-dia-a-dia)
6. [Resumo dos Comandos](#-6-resumo-dos-comandos)

---

## 🚀 1. Instalação e Pré-requisitos

### Requisitos:
* **Sistema Operacional:** Windows 10 ou 11 (Necessário para a biblioteca nativa do MetaTrader 5).
* **Python:** Versão 3.10 ou superior instalada.

### Clonar o Repositório e Instalar Dependências:
Abra o terminal (Prompt de Comando ou PowerShell) e execute:

```bash
# Clone o repositório (caso ainda não tenha clonado)
git clone https://github.com/devgtech01/Trading-Robot-Deep-Q-Learning.git
cd Trading-Robot-Deep-Q-Learning

# Instale todas as bibliotecas necessárias
pip install -r requirements.txt
```

---

## 📈 2. Configuração do MetaTrader 5 (XP Investimentos / B3)

Siga este passo a passo para conectar o robô de ações à sua conta da XP:

### Passo 2.1: Contratar o Simulador na XP
1. Acesse sua conta no site da **[XP Investimentos](https://www.xpi.com.br/)**.
2. Vá em **Bolsa** $\rightarrow$ **Plataformas de Negociação** (ou **Minha Conta** $\rightarrow$ **Contratação de Ferramentas**).
3. Localize **MetaTrader 5 (DMA2)** e clique em **Contratar** (custo R$ 0,00 / Gratuito).
4. Selecione a opção **Simulador / Conta Demo**.
5. A XP enviará no seu e-mail:
   * O link para baixar o instalador do MetaTrader 5;
   * O número do **Login da Conta Demo** (ex: `12345678`);
   * A **Senha do Simulador**;
   * O **Servidor** (geralmente `XPInvestimentos-PRD` ou `XPInvestimentos-DEMO`).

### Passo 2.2: Fazer Login no MetaTrader 5
1. Abra o aplicativo **MetaTrader 5** no seu computador.
2. No menu superior, clique em: **Arquivo** $\rightarrow$ **Login da Conta de Negociação**.
3. Preencha os campos com os dados recebidos da XP:
   * **Login:** Seu número da conta demo;
   * **Senha:** Sua senha do simulador;
   * **Servidor:** Selecione o servidor da XP (ex: `XPInvestimentos-PRD`).
4. Marque a opção **"Salvar senha"** e clique em **OK**.
5. No rodapé inferior direito do MT5, verifique se aparecem os números de conexão verdes indicando que está conectado ao vivo à B3.

### Passo 2.3: Habilitar a Negociação Automatizada no MT5 (CRUCIAL!)
* No topo da tela do MetaTrader 5, localize o botão **"AlgoTrading"** (ou **Negociação Automatizada**).
* Clique nele para que o ícone fique **VERDE com um triângulo de Play** ▶️. Sem isso, o MT5 bloqueará o envio de ordens pelo Python.

---

## 🪙 3. Configuração da Binance (Criptomoedas 24/7)

Siga este passo a passo para conectar o robô à Binance:

### Passo 3.1: Obter Chaves de Teste Gratuitas (Binance Testnet - Recomendado)
Para testar com **$ 10.000 USDT de mentira** sem nenhum risco financeiro:
1. Acesse o site oficial: **[https://testnet.binance.vision/](https://testnet.binance.vision/)**.
2. Clique no botão amarelo **"Generate API Key"** (autentique com sua conta do GitHub ou e-mail).
3. Copie a sua **API Key** e a sua **Secret Key** geradas na tela e guarde-as em um bloco de notas.

### Passo 3.2: Obter Chaves da Conta Real (Opcional - Somente quando for operar real)
1. Acesse sua conta na **[Binance](https://www.binance.com/)**.
2. Vá no seu **Perfil** $\rightarrow$ **Gerenciamento de API** $\rightarrow$ **Criar API**.
3. Marque **APENAS** as permissões:
   * ✅ **Leitura (Enable Reading)**
   * ✅ **Spot Trading (Enable Spot & Margin Trading)**
   * ❌ **NUNCA marque a opção de Saque (Enable Withdrawals)** por segurança.

---

## 🧠 4. Como Treinar os Modelos de IA

Antes de colocar os robôs para operar, você treina a rede neural DQN no histórico da ação ou criptomoeda desejada:

### A. Treinar em Ações da B3 (Treina 2018–2022 e Testa 2023–2026):
```bash
# Petrobras (PETR4)
python main.py --ticker PETR4.SA --episodes 20

# Vale (VALE3)
python main.py --ticker VALE3.SA --episodes 25

# WEG (WEGE3)
python main.py --ticker WEGE3.SA --episodes 20

# ETF do Ibovespa (BOVA11)
python main.py --ticker BOVA11.SA --episodes 20
```

### B. Treinar em Criptomoedas (Treina 2019–2023 e Testa 2024–2026):
```bash
# Bitcoin (BTC)
python main_crypto.py --ticker BTC-USD --episodes 25

# Ethereum (ETH)
python main_crypto.py --ticker ETH-USD --episodes 25

# Solana (SOL)
python main_crypto.py --ticker SOL-USD --episodes 20
```

> 📁 Os pesos treinados são salvos automaticamente na pasta `models/` e os relatórios gráficos de backtest com curvas de lucro na pasta `reports/`.

---

## ⚡ 5. Como Executar no Dia a Dia

Você pode utilizar o sistema em **3 modos diferentes**, dependendo do seu objetivo:

### MODO 1: Consulta Rápida de Sinais (Manual / Assistido)
Se você quer apenas saber a recomendação da IA para hoje e executar você mesmo no Home Broker:

```bash
# Para Ações B3:
python predict_today.py --ticker PETR4.SA

# Se você já tem a ação comprada a R$ 45.50:
python predict_today.py --ticker PETR4.SA --holding --buy-price 45.50

# Para Criptomoedas:
python predict_crypto.py --ticker BTC-USD
```

---

### MODO 2: Carteira Simulada Local (Paper Trading)
Executa compras e vendas virtuais simuladas no terminal, guardando seu extrato e saldo em `data/paper_wallet.json`:

```bash
# Simular operação em B3 (Saldo virtual de R$ 10.000):
python paper_trading.py --ticker PETR4.SA

# Simular operação em Cripto (Saldo virtual de $ 1.000 USDT):
python paper_trading.py --ticker BTC-USD
```

---

### MODO 3: Automação 100% Completa (Envio Direto de Ordens)

#### A. No MetaTrader 5 (XP Investimentos):
*Certifique-se de que o MT5 está aberto no seu computador com a conta logada e o botão AlgoTrading verde.*

```bash
# Executa 1 ciclo e envia a ordem se houver sinal:
python mt5_bot.py --ticker PETR4.SA --volume 100

# Deixar rodando o dia todo em segundo plano (verifica a cada 60 min):
python mt5_bot.py --ticker PETR4.SA --volume 100 --loop --interval-minutes 60
```

#### B. Na Binance (Spot Testnet):
```bash
# Executa 1 ciclo com $ 100 USDT por trade na Testnet:
python binance_bot.py --api-key SUA_API_KEY --secret-key SUA_SECRET_KEY --ticker BTC-USD --symbol BTCUSDT --amount 100

# Deixar rodando 24/7 em segundo plano (verifica a cada 60 min):
python binance_bot.py --api-key SUA_API_KEY --secret-key SUA_SECRET_KEY --ticker BTC-USD --symbol BTCUSDT --amount 100 --loop --interval-minutes 60
```

---

## 📌 6. Resumo dos Comandos

| Objetivo | Comando |
| :--- | :--- |
| **Treinar Ação B3** | `python main.py --ticker PETR4.SA --episodes 20` |
| **Treinar Cripto** | `python main_crypto.py --ticker BTC-USD --episodes 25` |
| **Consultar Sinal B3 Hoje** | `python predict_today.py --ticker PETR4.SA` |
| **Consultar Sinal Cripto Hoje** | `python predict_crypto.py --ticker BTC-USD` |
| **Simulador Local (Extrato)** | `python paper_trading.py --ticker PETR4.SA` |
| **Automação MetaTrader 5 (XP)** | `python mt5_bot.py --ticker PETR4.SA --volume 100` |
| **Automação Binance (Testnet)** | `python binance_bot.py --api-key KEY --secret-key SECRET --symbol BTCUSDT` |

---

## 🛡️ Gestão de Risco e Boas Práticas
1. **Sempre valide primeiro no Simulador**: Teste por no mínimo 2 a 4 semanas em modo simulador (MT5 Demo ou Binance Testnet) antes de colocar qualquer dinheiro real.
2. **Comece Pequeno**: Quando for operar em conta real, comece com o lote mínimo fracionário na B3 (1 a 10 ações com código `F`, ex: `PETR4F`) e frações mínimas em cripto ($ 10 a $ 20 USDT).
3. **Stop Loss**: Sempre configure regras de proteção e nunca aloque todo o seu capital em um único ativo.
