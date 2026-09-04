# Robô de Trading B3 com Deep Q-Learning (PyTorch)

Este projeto implementa um robô de Swing Trade autônomo baseado em **Aprendizado por Reforço Profundo (Deep Q-Learning / DQN)** para ações da B3 (mercado brasileiro), com simulação realista de custos operacionais, divisão rigorosa de treino vs. teste cego e relatórios gráficos completos.

---

## Como Executar na Prática

### 1. Treinar e Testar com uma Ação da B3

Para treinar o robô em dados históricos (2018 a 2022) e testá-lo automaticamente no período recente fora da amostra (2023 a 2026):

```bash
# Exemplo com Petrobras (PETR4)
python main.py --ticker PETR4.SA --episodes 20

# Exemplo com Vale (VALE3)
python main.py --ticker VALE3.SA --episodes 25

# Exemplo com WEG (WEGE3)
python main.py --ticker WEGE3.SA --episodes 20

# Exemplo com o ETF do Ibovespa (BOVA11)
python main.py --ticker BOVA11.SA --episodes 20
```

---

## Parâmetros Disponíveis

| Parâmetro | Padrão | Descrição |
| :--- | :--- | :--- |
| `--ticker` | `PETR4.SA` | Código da ação na B3 com sufixo `.SA` (ex: `PETR4.SA`, `VALE3.SA`, `ITUB4.SA`) |
| `--start-date` | `2018-01-01` | Data inicial do histórico para download e treino |
| `--split-date` | `2023-01-01` | Data de corte: antes é **Treino**, depois é **Teste Cego (Out-of-Sample)** |
| `--episodes` | `20` | Quantidade de episódios de treinamento |
| `--batch-size` | `32` | Tamanho da amostra da memória em cada passo de treino |
| `--capital` | `10000.0` | Capital inicial simulado em Reais (R$) |
| `--models-dir` | `models` | Pasta onde os pesos da rede neural (`.pt`) são salvos |
| `--reports-dir`| `reports` | Pasta onde os gráficos de backtest (`.png`) são gerados |

---

## Onde Encontrar os Resultados?

1. **Modelo Treinado**: Arquivo `.pt` salvo na pasta `models/` (ex: `models/PETR4_dqn.pt`).
2. **Relatório Gráfico**: Imagem de alta resolução salva na pasta `reports/` (ex: `reports/PETR4_backtest_report.png`), contendo:
   - **Curva de Capital**: Patrimônio líquido do robô ao longo do tempo comparado ao *Buy & Hold* do ativo;
   - **Preço e Execução**: Gráfico da cotação com os pontos exatos de entrada (triângulos verdes) e saída (triângulos vermelhos);
   - **Drawdown**: Gráfico da maior queda percentual de patrimônio ao longo do tempo.
