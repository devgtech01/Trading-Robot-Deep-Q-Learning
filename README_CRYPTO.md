# Robô de Trading de Criptomoedas com Deep Q-Learning (PyTorch)

Este módulo implementa um robô autônomo baseado em **Aprendizado por Reforço Profundo (Deep Q-Learning / DQN)** calibrado para o mercado de **Criptomoedas (24/7)**, operando em pares contra Dólar / USDT (ex: `BTC-USD`, `ETH-USD`, `SOL-USD`).

---

## Como Usar na Prática

### 1. Treinar e Fazer Backtest em Criptomoedas

Para treinar o robô no histórico (ex: 2019 a 2023) e testá-lo no período recente fora da amostra (2024 a 2026):

```bash
# Treinar no Bitcoin (BTC)
python main_crypto.py --ticker BTC-USD --episodes 25

# Treinar no Ethereum (ETH)
python main_crypto.py --ticker ETH-USD --episodes 25

# Treinar na Solana (SOL)
python main_crypto.py --ticker SOL-USD --episodes 20
```

---

### 2. Consultar o Sinal de Hoje ao Vivo

Para saber se o robô recomenda Comprar, Vender ou Ficar em USDT no dia de hoje:

```bash
# Consulta geral (se você estiver líquido em USDT):
python predict_crypto.py --ticker BTC-USD

# Consulta se você já comprou Bitcoin (ex: a $ 62.000):
python predict_crypto.py --ticker BTC-USD --holding --buy-price 62000
```

---

## Parâmetros Disponíveis

| Parâmetro | Padrão | Descrição |
| :--- | :--- | :--- |
| `--ticker` | `BTC-USD` | Par da cripto (ex: `BTC-USD`, `ETH-USD`, `SOL-USD`, `BNB-USD`, `XRP-USD`) |
| `--start-date` | `2019-01-01` | Início do histórico de treino |
| `--split-date` | `2024-01-01` | Data de corte para o teste cego (out-of-sample) |
| `--episodes` | `25` | Quantidade de episódios de treinamento |
| `--capital` | `1000.0` | Capital inicial em USDT ($) |
| `--models-dir` | `models` | Pasta onde os pesos da rede neural (`.pt`) são salvos |
| `--reports-dir`| `reports` | Pasta onde os gráficos de backtest (`.png`) são salvos |
