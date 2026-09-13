/* ==========================================================================
 *  Painel do Robô de Trading DQN — lógica da interface
 * ========================================================================== */

const State = {
    overview: null,
    view: "stocks",
    assetForm: { mode: "create", ticker: null },
    train: { ticker: null, jobId: null, logCursor: 0, timer: null },
    run: { ticker: null },
    refreshing: false,
};

const MODE_LABELS = {
    signal: "Somente sinal (não envia ordem)",
    paper: "Carteira simulada (paper)",
    mt5: "MetaTrader 5 — dinheiro real",
    binance_testnet: "Binance Testnet (simulado)",
    binance_real: "Binance conta REAL",
};
const MODE_SHORT = {
    signal: "Sinal", paper: "Paper", mt5: "MT5", binance_testnet: "Testnet", binance_real: "Binance real",
};
const REAL_MODES = ["mt5", "binance_real"];
const ACTION_CLASS = { 0: "hold", 1: "buy", 2: "sell" };
const ACTION_ICON = { hold: "hold", buy: "buy", sell: "sell" };
const TOAST_ICON = { success: "check", error: "alert", warning: "alert", info: "info" };

/* ------------------------------- Utilidades ------------------------------ */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function money(value, symbol = "R$", digits = 2) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    return `${symbol} ${Number(value).toLocaleString("pt-BR", {
        minimumFractionDigits: digits, maximumFractionDigits: digits,
    })}`;
}

function qty(value, digits = 6) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString("pt-BR", { maximumFractionDigits: digits });
}

function pct(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    const n = Number(value);
    return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

const signClass = (v) => (Number(v) >= 0 ? "pos" : "neg");

function note(kind, html, iconName) {
    const glyph = iconName || { risk: "alert", warn: "alert", good: "check" }[kind] || "info";
    return `<div class="note ${kind}">${icon(glyph, 16)}<span>${html}</span></div>`;
}

function toast(message, type = "info", ms = 4400) {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.innerHTML = `${icon(TOAST_ICON[type] || "info", 15)}<span>${esc(message)}</span>`;
    $("#toasts").appendChild(el);
    setTimeout(() => el.remove(), ms);
}

async function api(path, options = {}) {
    const res = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
        body: options.body ? JSON.stringify(options.body) : undefined,
    });
    let data;
    try {
        data = await res.json();
    } catch (err) {
        throw new Error(`Resposta inválida do servidor (${res.status})`);
    }
    if (!res.ok || data.ok === false) throw new Error(data.error || `Erro ${res.status}`);
    return data;
}

function openModal(id) { $(`#${id}`).classList.add("open"); }
function closeModal(id) { $(`#${id}`).classList.remove("open"); }

/* --------------------------- Carregamento geral -------------------------- */
async function loadOverview(refresh = false) {
    if (State.refreshing) return;
    State.refreshing = true;
    $("#btn-refresh").innerHTML = '<span class="spinner"></span>';
    try {
        const data = await api(`/api/overview${refresh ? "?refresh=1" : ""}`);
        State.overview = data;
        renderAll();
    } catch (err) {
        toast(`Falha ao carregar o painel: ${err.message}`, "error");
    } finally {
        State.refreshing = false;
        $("#btn-refresh").innerHTML = icon("refresh", 16);
    }
}

function renderAll() {
    const o = State.overview;
    if (!o) return;
    renderTopbar(o);
    renderGrid("stocks", o.stocks);
    renderGrid("crypto", o.crypto);
    renderWallet(o.portfolio);
    renderAutomation(o);
    renderActivity(o.activity);
    renderSettings(o.settings);
    loadHistory();
}

/* -------------------------------- Topbar -------------------------------- */
function renderTopbar(o) {
    const brl = o.portfolio.BRL, usdt = o.portfolio.USDT;
    $("#top-equity-brl").innerHTML =
        `${money(brl.equity, "R$")}<span class="delta ${signClass(brl.total_return_pct)}">${pct(brl.total_return_pct)}</span>`;
    $("#top-equity-usdt").innerHTML =
        `${money(usdt.equity, "$")}<span class="delta ${signClass(usdt.total_return_pct)}">${pct(usdt.total_return_pct)}</span>`;

    const master = o.automation.master_enabled;
    $("#master-switch").checked = master;
    $("#master-label").textContent = master
        ? `Automação ativa · ${o.automation.active_count} ativo${o.automation.active_count === 1 ? "" : "s"}`
        : "Automação desligada";

    $("#count-stocks").textContent = o.stocks.length;
    $("#count-crypto").textContent = o.crypto.length;
    $("#count-auto").textContent = o.automation.active_count;
}

/* ------------------------------ Cards ----------------------------------- */
function sparkline(series) {
    if (!series || series.length < 2) return "";
    const min = Math.min(...series), max = Math.max(...series);
    const span = max - min || 1;
    const points = series
        .map((v, i) => `${(i / (series.length - 1)) * 100},${34 - ((v - min) / span) * 30}`)
        .join(" ");
    const up = series[series.length - 1] >= series[0];
    const stroke = up ? "var(--gain)" : "var(--loss)";
    return `<svg class="spark" viewBox="0 0 100 38" preserveAspectRatio="none" aria-hidden="true">
        <polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="1.25"
                  vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
    </svg>`;
}

function qBars(q) {
    const entries = [["Aguardar", "hold", q.hold], ["Comprar", "buy", q.buy], ["Vender", "sell", q.sell]];
    const values = entries.map((e) => e[2]);
    const min = Math.min(...values), max = Math.max(...values);
    const span = max - min || 1;
    return `<div class="qbars">${entries.map(([name, key, value]) => {
        const width = ((value - min) / span) * 100;
        return `<div class="qbar ${value === max ? "lead" : ""}">
            <span class="qname">${name}</span>
            <span class="qtrack"><span class="qfill ${key}" style="width:${Math.max(2, width)}%"></span></span>
            <span class="qval">${value >= 0 ? "+" : ""}${value.toFixed(3)}</span>
        </div>`;
    }).join("")}</div>`;
}

function assetCard(asset) {
    const crypto = asset.asset_class === "crypto";
    const sym = asset.currency_symbol;
    const s = asset.signal || {};
    const auto = asset.automation;
    const job = asset.running_job;

    // --- sinal ---
    let signalBlock;
    if (!asset.model.trained) {
        signalBlock = `<div class="signal none">
            <span class="glyph">${icon("alert", 16)}</span>
            <span class="label">Modelo não treinado</span>
            <span class="hint">Treine para liberar os sinais</span>
        </div>`;
    } else if (!s.available) {
        signalBlock = `<div class="signal none">
            <span class="glyph">${icon("alert", 16)}</span>
            <span class="label">Sinal indisponível</span>
            <span class="hint">${esc(s.message || "erro ao calcular")}</span>
        </div>`;
    } else {
        const cls = ACTION_CLASS[s.action];
        signalBlock = `<div class="signal ${cls}">
            <span class="glyph">${icon(ACTION_ICON[cls], 16)}</span>
            <span class="label">${esc(s.action_label)}</span>
            <span class="hint">${s.filtered ? `rede indica ${esc(s.raw_action_label.toLowerCase())}<br>` : ""}
                fech. <span class="figure">${esc(s.quote_date)}</span></span>
        </div>`;
    }

    // --- indicadores ---
    let metrics = "";
    if (s.available) {
        const ind = s.indicators;
        const extra = crypto
            ? `<div class="metric"><div class="k">%B Boll</div><div class="v">${ind.bollinger_pct_b.toFixed(0)}</div></div>`
            : `<div class="metric"><div class="k">Vol 10d</div><div class="v">${ind.volatility.toFixed(1)}</div></div>`;
        metrics = `<div class="metrics">
            <div class="metric"><div class="k">RSI 14</div><div class="v">${ind.rsi.toFixed(0)}</div></div>
            <div class="metric"><div class="k">vs SMA21</div><div class="v ${signClass(ind.dist_sma21)}">${pct(ind.dist_sma21, 1)}</div></div>
            <div class="metric"><div class="k">5 dias</div><div class="v ${signClass(ind.return_5d)}">${pct(ind.return_5d, 1)}</div></div>
            ${extra}
        </div>`;
    }

    // --- posição aberta ---
    let position = "";
    if (asset.position) {
        const p = asset.position;
        const price = s.available ? s.price : p.buy_price;
        const pnl = ((price - p.buy_price) / p.buy_price) * 100;
        position = `<div class="pos-line">
            <span class="tag live"><span class="pip"></span>Posição</span>
            <span class="qty">${qty(p.amount)} @ ${money(p.buy_price, sym)}</span>
            <span class="res ${signClass(pnl)}">${pct(pnl)}</span>
            <button class="tiny ghost" data-act="close" data-ticker="${esc(asset.ticker)}"
                title="Encerrar esta posição agora">Encerrar</button>
        </div>`;
    }

    // --- etiquetas ---
    const autoTag = auto.enabled
        ? `<span class="tag ${REAL_MODES.includes(auto.mode) ? "risk" : "live"}">
             <span class="pip beat"></span>${esc(MODE_SHORT[auto.mode])} · ${auto.interval_minutes}m</span>`
        : `<span class="tag">Robô parado</span>`;

    const jobTag = job
        ? `<span class="tag accent"><span class="spinner" style="width:8px;height:8px;border-width:1.2px"></span>
             Treinando ${Math.round(job.progress)}%</span>`
        : "";

    const change = s.available
        ? `<div class="change ${signClass(s.price_change_pct)}">${pct(s.price_change_pct)}</div>`
        : "";

    return `<article class="card" data-ticker="${esc(asset.ticker)}">
        <div class="card-head">
            <div class="ident">
                <div class="ticker">${esc(asset.ticker)}</div>
                <div class="name">${esc(asset.name)}</div>
            </div>
            <div class="price-box">
                <div class="price">${s.available ? money(s.price, sym) : "—"}</div>
                ${change}
            </div>
        </div>

        <div class="tags">
            <span class="tag">${icon(crypto ? "crypto" : "equities", 14)}${crypto ? "Cripto" : "Ação B3"}</span>
            ${autoTag}
            ${jobTag}
            ${asset.model.trained ? "" : `<span class="tag warn">Sem modelo</span>`}
        </div>

        ${signalBlock}
        ${s.available ? qBars(s.q_values) : ""}
        ${metrics}
        <div class="spark-slot" data-spark="${esc(asset.ticker)}"></div>
        ${position}

        <div class="card-foot">
            <button class="tiny success" data-act="run" data-ticker="${esc(asset.ticker)}"
                ${asset.model.trained ? "" : "disabled"}>${icon("play", 14)} Executar</button>
            <button class="tiny" data-act="train" data-ticker="${esc(asset.ticker)}"
                title="${asset.model.trained
                    ? `Retreinar — modelo atual de ${esc(asset.model.trained_at)}`
                    : "Treinar o modelo deste ativo"}">${icon("train", 14)} Treinar</button>
            <button class="tiny" data-act="report" data-ticker="${esc(asset.ticker)}"
                ${asset.has_report ? "" : "disabled"}>${icon("chart", 14)} Backtest</button>
            <span class="foot-actions push">
                <button class="tiny ghost" data-act="edit" data-ticker="${esc(asset.ticker)}"
                    title="Editar ativo">${icon("edit", 14)}</button>
                <button class="tiny ghost" data-act="delete" data-ticker="${esc(asset.ticker)}"
                    title="Remover do catálogo">${icon("trash", 14)}</button>
            </span>
        </div>
    </article>`;
}

function renderGrid(kind, assets) {
    const grid = $(`#grid-${kind}`);
    if (!assets.length) {
        grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
            Nenhum ${kind === "stocks" ? "ativo da B3" : "par de cripto"} cadastrado ainda.
        </div>`;
        return;
    }
    grid.innerHTML = assets.map(assetCard).join("");
    assets.forEach((a) => loadSpark(a.ticker));
}

const sparkCache = {};
async function loadSpark(ticker) {
    const slot = document.querySelector(`.spark-slot[data-spark="${CSS.escape(ticker)}"]`);
    if (!slot) return;
    if (sparkCache[ticker]) {
        slot.innerHTML = sparkline(sparkCache[ticker]);
        return;
    }
    try {
        const data = await api(`/api/assets/${encodeURIComponent(ticker)}/series?points=90`);
        sparkCache[ticker] = data.series.closes;
        const target = document.querySelector(`.spark-slot[data-spark="${CSS.escape(ticker)}"]`);
        if (target) target.innerHTML = sparkline(sparkCache[ticker]);
    } catch (err) { /* o gráfico é opcional */ }
}

/* ------------------------------ Carteira -------------------------------- */
function renderWallet(portfolio) {
    $("#wallet-accounts").innerHTML = Object.values(portfolio).map((acc) => {
        const stock = acc.currency === "BRL";
        const rows = acc.positions.length
            ? acc.positions.map((p) => `<tr>
                <td><strong>${esc(p.ticker)}</strong></td>
                <td class="num">${qty(p.amount)}</td>
                <td class="num">${money(p.buy_price, acc.symbol)}</td>
                <td class="num">${money(p.current_price, acc.symbol)}</td>
                <td class="num">${money(p.market_value, acc.symbol)}</td>
                <td class="num ${signClass(p.pnl_cash)}">${money(p.pnl_cash, acc.symbol)}</td>
                <td class="num ${signClass(p.pnl_pct)}">${pct(p.pnl_pct)}</td>
              </tr>`).join("")
            : `<tr><td colspan="7" class="faint" style="text-align:center;padding:24px">Nenhuma posição aberta.</td></tr>`;

        return `<div class="panel">
            <div class="section-head" style="margin-bottom:0">
                <h3>${icon(stock ? "equities" : "crypto", 16)} Conta ${stock ? "Ações · BRL" : "Cripto · USDT"}</h3>
                <span class="spacer"></span>
                <button class="tiny" data-wallet="deposit" data-currency="${acc.currency}">${icon("plus", 13)} Aporte</button>
                <button class="tiny danger" data-wallet="reset" data-currency="${acc.currency}">Reiniciar</button>
            </div>
            <div class="stat-row">
                <div class="stat"><div class="k">Patrimônio</div><div class="v">${money(acc.equity, acc.symbol)}</div></div>
                <div class="stat"><div class="k">Caixa</div><div class="v">${money(acc.cash, acc.symbol)}</div></div>
                <div class="stat"><div class="k">Investido</div><div class="v">${money(acc.invested, acc.symbol)}</div></div>
                <div class="stat"><div class="k">Retorno</div>
                    <div class="v ${signClass(acc.total_return_pct)}">${pct(acc.total_return_pct)}</div></div>
                <div class="stat"><div class="k">Realizado</div>
                    <div class="v ${signClass(acc.realized_pnl)}">${money(acc.realized_pnl, acc.symbol)}</div></div>
                <div class="stat"><div class="k">Trades · acerto</div>
                    <div class="v">${acc.closed_trades} · ${acc.win_rate_pct.toFixed(0)}%</div></div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>Ativo</th><th class="num">Quantidade</th><th class="num">Preço médio</th>
                        <th class="num">Atual</th><th class="num">Valor</th>
                        <th class="num">Resultado</th><th class="num">%</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
    }).join("");
}

/* ----------------------------- Automação -------------------------------- */
function renderAutomation(o) {
    const a = o.automation;
    $("#automation-status").innerHTML = `
        <div class="stat"><div class="k">Chave-geral</div>
            <div class="v text ${a.master_enabled ? "pos" : "faint"}">${a.master_enabled ? "Ligada" : "Desligada"}</div></div>
        <div class="stat"><div class="k">Agendador</div>
            <div class="v text ${a.scheduler_running ? "pos" : "neg"}">${a.scheduler_running ? "Ativo" : "Parado"}</div></div>
        <div class="stat"><div class="k">Robôs ligados</div><div class="v">${a.active_count}</div></div>
        <div class="stat"><div class="k">Em corretora</div>
            <div class="v ${a.live_count ? "neg" : ""}">${a.live_count}</div></div>
        <div class="stat"><div class="k">Dinheiro real</div>
            <div class="v text ${a.allow_real_money ? "neg" : "pos"}">${a.allow_real_money ? "Liberado" : "Bloqueado"}</div></div>
        <div class="stat"><div class="k">Hora do servidor</div>
            <div class="v">${esc(a.server_time.slice(11))}</div></div>`;

    $("#automation-warning").innerHTML = a.master_enabled && a.live_count
        ? note("risk", `<strong>${a.live_count} ativo(s)</strong> enviando ordens para corretora. Acompanhe o registro de atividades.`)
        : (!a.master_enabled && a.active_count
            ? note("warn", `A chave-geral está desligada: os ${a.active_count} robô(s) marcados não vão rodar.`)
            : "");

    const assets = [...o.stocks, ...o.crypto];
    $("#automation-rows").innerHTML = assets.length ? assets.map((asset) => {
        const auto = asset.automation;
        const options = asset.available_modes.map((m) =>
            `<option value="${m}" ${m === auto.mode ? "selected" : ""}>${esc(MODE_LABELS[m])}</option>`).join("");
        const size = asset.asset_class === "crypto"
            ? money(asset.quantity, "$")
            : `${qty(asset.quantity, 0)} un.`;
        return `<tr>
            <td><strong>${esc(asset.ticker)}</strong><div class="sub">${esc(asset.name)}</div></td>
            <td><span class="tag">${icon(asset.asset_class === "crypto" ? "crypto" : "equities", 13)}
                ${asset.asset_class === "crypto" ? "Cripto" : "Ação"}</span></td>
            <td><label class="switch">
                    <input type="checkbox" data-auto="enabled" data-ticker="${esc(asset.ticker)}"
                        ${auto.enabled ? "checked" : ""} ${asset.model.trained ? "" : "disabled"}>
                    <span class="track"></span>
                </label></td>
            <td><select data-auto="mode" data-ticker="${esc(asset.ticker)}" style="min-width:250px">${options}</select></td>
            <td class="num"><input type="number" min="1" max="1440" value="${auto.interval_minutes}"
                    data-auto="interval" data-ticker="${esc(asset.ticker)}" style="width:74px;text-align:right"></td>
            <td class="num">${size}</td>
            <td class="num">${esc(auto.last_run ? auto.last_run.slice(5, 16) : "—")}</td>
            <td class="num">${auto.enabled ? esc(auto.next_run ? auto.next_run.slice(5, 16) : "em breve") : "—"}</td>
            <td style="white-space:normal;max-width:270px" class="small faint">${esc(auto.last_result || "—")}</td>
            <td><button class="tiny ghost" data-act="run" data-ticker="${esc(asset.ticker)}"
                title="Executar ciclo agora" ${asset.model.trained ? "" : "disabled"}>${icon("play", 13)}</button></td>
        </tr>`;
    }).join("") : `<tr><td colspan="10" class="faint" style="text-align:center;padding:32px">Nenhum ativo cadastrado.</td></tr>`;
}

/* ------------------------------ Histórico -------------------------------- */
async function loadHistory() {
    try {
        const rows = (await api("/api/history?limit=100")).history;
        $("#history-rows").innerHTML = rows.length ? rows.map((h) => `<tr>
            <td><strong>${esc(h.ticker)}</strong></td>
            <td><span class="tag">${esc(h.currency)}</span></td>
            <td class="num faint">${esc((h.buy_date || "").slice(0, 16))}</td>
            <td class="num">${money(h.buy_price, h.symbol)}</td>
            <td class="num faint">${esc((h.sell_date || "").slice(0, 16))}</td>
            <td class="num">${money(h.sell_price, h.symbol)}</td>
            <td class="num">${qty(h.amount)}</td>
            <td class="num ${signClass(h.profit_cash)}">${money(h.profit_cash, h.symbol)}</td>
            <td class="num ${signClass(h.profit_pct)}">${pct(h.profit_pct)}</td>
        </tr>`).join("")
            : `<tr><td colspan="9" class="faint" style="text-align:center;padding:32px">Nenhuma operação fechada ainda.</td></tr>`;
    } catch (err) { /* silencioso */ }
}

function renderActivity(entries) {
    $("#activity-list").innerHTML = (entries && entries.length)
        ? entries.map((e) => `<div class="activity-item ${esc(e.level)}">
            <span class="lv"></span>
            <span class="ts">${esc(e.timestamp.slice(5, 16))}</span>
            <span class="msg">${esc(e.message)}</span>
        </div>`).join("")
        : `<div class="empty" style="border:0">Sem atividade registrada.</div>`;
}

/* ---------------------------- Configurações ------------------------------ */
function renderSettings(settings) {
    $("#cfg-binance-status").innerHTML = settings.binance_configured
        ? `<span class="pos" style="display:inline-flex;align-items:center;gap:6px">
             ${icon("check", 14)} Chaves salvas · ${esc(settings.binance_api_key_masked)}</span>`
        : `<span class="faint" style="display:inline-flex;align-items:center;gap:6px">
             ${icon("alert", 14)} Nenhuma chave configurada</span>`;
    $("#cfg-real-money").checked = settings.allow_real_money;
    $("#cfg-real-money-label").textContent = settings.allow_real_money
        ? "Liberada — ordens reais permitidas"
        : "Bloqueada";
    $("#cfg-cache").value = settings.quote_cache_minutes;
}

/* ------------------------- Modal: editor de ativo ------------------------ */
function openAssetModal(assetClass, asset = null) {
    State.assetForm = { mode: asset ? "edit" : "create", ticker: asset ? asset.ticker : null };
    const crypto = (asset ? asset.asset_class : assetClass) === "crypto";

    $("#asset-modal-title").textContent = asset ? `Editar ${asset.ticker}` : "Adicionar ativo";
    $("#af-ticker").value = asset ? asset.ticker : "";
    $("#af-ticker").disabled = !!asset;
    $("#af-name").value = asset ? asset.name : "";
    $("#af-class").value = crypto ? "crypto" : "stock";
    $("#af-symbol").value = asset ? asset.broker_symbol : "";
    $("#af-qty").value = asset ? asset.quantity : 100;
    $("#af-start").value = asset ? asset.start_date : (crypto ? "2019-01-01" : "2018-01-01");
    $("#af-split").value = asset ? asset.split_date : (crypto ? "2024-01-01" : "2023-01-01");
    updateAssetHint();
    openModal("modal-asset");
}

function updateAssetHint() {
    const crypto = $("#af-class").value === "crypto";
    $("#af-qty-wrap").firstChild.textContent = crypto ? "Valor por ordem (USDT) " : "Ações por ordem ";
    $("#af-hint").innerHTML = crypto
        ? "Ticker no formato do Yahoo Finance (BTC-USD) e símbolo da Binance em BTCUSDT. O tamanho da ordem é o valor em USDT gasto a cada compra."
        : "Ticker da B3 com sufixo .SA (PETR4.SA) e símbolo do MetaTrader 5 sem sufixo (PETR4, ou PETR4F para fracionário). O tamanho da ordem é a quantidade de ações.";
}

async function saveAsset() {
    const ticker = $("#af-ticker").value.trim().toUpperCase();
    if (!ticker) return toast("Informe o ticker.", "error");
    const payload = {
        ticker,
        name: $("#af-name").value.trim() || ticker,
        asset_class: $("#af-class").value,
        broker_symbol: $("#af-symbol").value.trim(),
        quantity: parseFloat($("#af-qty").value) || 0,
        start_date: $("#af-start").value.trim(),
        split_date: $("#af-split").value.trim(),
    };
    try {
        await api("/api/assets", { method: "POST", body: payload });
        closeModal("modal-asset");
        toast(`Ativo ${ticker} salvo.`, "success");
        delete sparkCache[ticker];
        loadOverview();
    } catch (err) {
        toast(err.message, "error");
    }
}

/* --------------------------- Modal: treinamento -------------------------- */
function openTrainModal(asset) {
    State.train = { ticker: asset.ticker, jobId: null, logCursor: 0, timer: null };
    $("#train-title").textContent = `Treinar modelo — ${asset.ticker}`;
    $("#tf-capital").value = asset.asset_class === "crypto" ? 1000 : 10000;
    $("#tf-episodes").value = 20;
    $("#tf-batch").value = 32;
    $("#train-form").style.display = "";
    $("#train-progress").style.display = "none";
    $("#train-log").textContent = "";
    $("#train-result").innerHTML = "";
    $("#btn-train-start").style.display = "";
    $("#btn-train-cancel").style.display = "none";
    openModal("modal-train");

    if (asset.running_job) attachJob(asset.running_job.id);
}

async function startTraining() {
    const ticker = State.train.ticker;
    try {
        const data = await api(`/api/assets/${encodeURIComponent(ticker)}/train`, {
            method: "POST",
            body: {
                episodes: parseInt($("#tf-episodes").value, 10),
                batch_size: parseInt($("#tf-batch").value, 10),
                capital: parseFloat($("#tf-capital").value),
            },
        });
        toast(`Treinamento de ${ticker} iniciado.`, "success");
        attachJob(data.job.id);
    } catch (err) {
        toast(err.message, "error");
    }
}

function attachJob(jobId) {
    State.train.jobId = jobId;
    State.train.logCursor = 0;
    $("#train-form").style.display = "none";
    $("#train-progress").style.display = "";
    $("#btn-train-start").style.display = "none";
    $("#btn-train-cancel").style.display = "";
    $("#train-log").textContent = "";
    clearInterval(State.train.timer);
    State.train.timer = setInterval(pollJob, 1500);
    pollJob();
}

async function pollJob() {
    if (!State.train.jobId) return;
    try {
        const job = (await api(`/api/jobs/${State.train.jobId}?log_from=${State.train.logCursor}`)).job;
        State.train.logCursor = job.log_total;

        if (job.log.length) {
            const log = $("#train-log");
            log.textContent += (log.textContent ? "\n" : "") + job.log.join("\n");
            log.scrollTop = log.scrollHeight;
        }
        $("#train-stage").textContent = job.stage;
        $("#train-pct").textContent = `${job.progress}%`;
        $("#train-bar").style.width = `${job.progress}%`;

        if (job.status !== "running") {
            clearInterval(State.train.timer);
            $("#btn-train-cancel").style.display = "none";
            if (job.status === "done" && job.result) {
                renderTrainResult(job);
                toast(`Treinamento de ${job.ticker} concluído.`, "success");
            } else if (job.status === "error") {
                $("#train-result").innerHTML = note("risk", `Erro: ${esc(job.error)}`);
                toast(`Falha no treinamento de ${job.ticker}.`, "error");
            } else {
                $("#train-result").innerHTML = note("warn", "Treinamento cancelado.");
            }
            delete sparkCache[job.ticker];
            loadOverview();
        }
    } catch (err) {
        clearInterval(State.train.timer);
    }
}

function renderTrainResult(job) {
    const m = job.result.metrics;
    const beat = m.total_return_pct >= m.benchmark_return_pct;
    $("#train-result").innerHTML = `
        ${note(beat ? "good" : "warn",
            `<strong>Teste cego (out-of-sample)</strong> — o robô ${beat ? "superou" : "ficou abaixo do"} Buy &amp; Hold.`)}
        <div class="stat-row">
            <div class="stat"><div class="k">Retorno robô</div>
                <div class="v ${signClass(m.total_return_pct)}">${pct(m.total_return_pct)}</div></div>
            <div class="stat"><div class="k">Buy &amp; Hold</div>
                <div class="v ${signClass(m.benchmark_return_pct)}">${pct(m.benchmark_return_pct)}</div></div>
            <div class="stat"><div class="k">Drawdown</div>
                <div class="v neg">${pct(m.max_drawdown_pct)}</div></div>
            <div class="stat"><div class="k">Sharpe</div><div class="v">${Number(m.sharpe_ratio).toFixed(2)}</div></div>
            <div class="stat"><div class="k">Trades</div><div class="v">${m.total_trades}</div></div>
            <div class="stat"><div class="k">Acerto</div><div class="v">${Number(m.win_rate_pct).toFixed(1)}%</div></div>
        </div>
        <button class="primary" data-act="report" data-ticker="${esc(job.ticker)}">
            ${icon("chart", 14)} Ver relatório gráfico</button>`;
}

/* ---------------------- Modal: execução manual --------------------------- */
function openRunModal(asset, opts = {}) {
    const closing = !!opts.close && !!asset.position;
    State.run = { ticker: asset.ticker, asset, sizing: null, closing };
    $("#run-title").textContent = closing
        ? `Encerrar posição — ${asset.ticker}`
        : `Executar ciclo — ${asset.ticker}`;
    $("#btn-run-confirm").innerHTML = closing
        ? `${icon("sell", 14)} Encerrar posição`
        : `${icon("play", 14)} Executar ciclo`;
    $("#btn-run-confirm").className = closing ? "danger" : "primary";

    const s = asset.signal || {};
    const cls = s.available ? ACTION_CLASS[s.action] : null;
    const isBuy = !closing && s.available && s.action === 1;

    if (closing) return renderCloseModal(asset);
    const options = asset.available_modes.map((m) =>
        `<option value="${m}" ${m === asset.automation.mode ? "selected" : ""}>${esc(MODE_LABELS[m])}</option>`).join("");

    $("#run-body").innerHTML = `
        ${s.available ? `<div class="signal ${cls}">
            <span class="glyph">${icon(ACTION_ICON[cls], 16)}</span>
            <span class="label">${esc(s.action_label)}</span>
            <span class="hint"><span class="figure">${money(s.price, asset.currency_symbol)}</span><br>
                fech. ${esc(s.quote_date)}</span>
        </div>` : note("warn", "Sinal ainda não calculado para este ativo.")}

        <label class="field">Destino da execução
            <select id="run-mode">${options}</select>
        </label>

        ${isBuy ? `
        <div>
            <label class="field" for="run-qty">Tamanho desta ordem</label>
            <div class="size-row">
                <input type="number" id="run-qty" step="any" min="0"
                       value="${asset.asset_class === "crypto" ? asset.quantity : Math.round(asset.quantity)}">
                <span class="unit">${asset.asset_class === "crypto" ? "USDT" : "ações"}</span>
                <button class="tiny" id="btn-use-suggested" disabled>usar sugerido</button>
            </div>
            <p class="small faint" id="run-qty-hint" style="margin:7px 0 0"></p>
        </div>
        <div id="run-advice"><div class="advice-loading">
            <span class="spinner"></span> Calculando o tamanho recomendado a partir do backtest…
        </div></div>` : `
        <p class="small faint" style="margin:0">${
            s.available && s.action === 2
                ? "Vendas encerram a posição inteira: o modelo foi treinado tudo-dentro/tudo-fora, então não existe venda parcial."
                : "O ciclo baixa a cotação mais recente, recalcula o sinal considerando sua posição atual e aplica a decisão no destino escolhido."
        }</p>`}

        <div id="run-warning"></div>
        <div id="run-result"></div>`;

    $("#run-mode").addEventListener("change", updateRunWarning);
    updateRunWarning();
    openModal("modal-run");

    if (isBuy) {
        $("#run-qty").addEventListener("input", updateQtyHint);
        $("#btn-use-suggested").addEventListener("click", () => {
            const sz = State.run.sizing;
            if (!sz) return;
            $("#run-qty").value = sz.suggested_units;
            updateQtyHint();
        });
        updateQtyHint();
        loadSizing(asset);
    }
}

function renderCloseModal(asset) {
    const p = asset.position;
    const s = asset.signal || {};
    const sym = asset.currency_symbol;
    const price = s.available ? s.price : p.buy_price;
    const valor = p.amount * price;
    const custo = p.cost_basis;
    const resultado = valor - custo;
    const pnl = (resultado / custo) * 100;

    const options = asset.available_modes
        .filter((m) => m !== "signal")   // "somente sinal" não encerra nada
        .map((m) => `<option value="${m}" ${m === "paper" ? "selected" : ""}>${esc(MODE_LABELS[m])}</option>`)
        .join("");

    $("#run-body").innerHTML = `
        <div class="stat-row" style="margin:0">
            <div class="stat"><div class="k">Quantidade</div><div class="v">${qty(p.amount)}</div></div>
            <div class="stat"><div class="k">Preço de compra</div><div class="v">${money(p.buy_price, sym)}</div></div>
            <div class="stat"><div class="k">Preço agora</div><div class="v">${money(price, sym)}</div></div>
            <div class="stat"><div class="k">Resultado</div>
                <div class="v ${signClass(resultado)}">${money(resultado, sym)}</div></div>
            <div class="stat"><div class="k">Variação</div>
                <div class="v ${signClass(pnl)}">${pct(pnl)}</div></div>
        </div>

        <label class="field">Onde encerrar
            <select id="run-mode">${options}</select>
        </label>

        ${note("warn", `A venda é da posição inteira e o resultado de
            <strong>${money(resultado, sym)}</strong> vira definitivo.
            ${s.available && s.action !== 2
                ? `O modelo hoje diz <strong>${esc(s.action_label)}</strong> — encerrar agora é uma decisão sua, contra o sinal.`
                : ""}`)}

        <div id="run-warning"></div>
        <div id="run-result"></div>`;

    $("#run-mode").addEventListener("change", updateRunWarning);
    updateRunWarning();
    openModal("modal-run");
}

function updateQtyHint() {
    const { asset, sizing: sz } = State.run;
    const input = $("#run-qty");
    if (!input) return;

    const value = parseFloat(input.value) || 0;
    const crypto = asset.asset_class === "crypto";
    const sym = asset.currency_symbol;
    const price = asset.signal.price || 0;
    const notional = crypto ? value : value * price;

    let hint = crypto
        ? `${money(notional, sym)} · ${(notional / (price || 1)).toFixed(6)} ${asset.ticker.split("-")[0]}`
        : `${money(notional, sym)} · ${money(price, sym)} por ação`;

    const excede = sz && notional > sz.cash;
    if (sz) {
        hint += ` · caixa livre ${money(sz.cash, sym)}`;
        if (excede) hint += " — acima do caixa, a ordem seria recusada";
    }
    const el = $("#run-qty-hint");
    el.textContent = hint;
    el.className = excede ? "small neg" : "small faint";
}

async function loadSizing(asset) {
    try {
        const data = await api(`/api/assets/${encodeURIComponent(asset.ticker)}/sizing`);
        State.run.sizing = data.sizing;
        renderAdvice(asset, data.sizing);
        $("#btn-use-suggested").disabled = !(data.sizing.suggested_units > 0);
        updateQtyHint();
    } catch (err) {
        $("#run-advice").innerHTML = note("warn",
            `Não foi possível calcular a recomendação: ${esc(err.message)}`);
    }
}

function renderAdvice(asset, sz) {
    const sym = asset.currency_symbol;
    const crypto = asset.asset_class === "crypto";
    const m = sz.metrics;

    const size = crypto
        ? money(sz.suggested_units, sym)
        : `${qty(sz.suggested_units, 0)} ações <span class="faint">≈ ${money(sz.suggested_notional, sym)}</span>`;

    const evidencia = m ? `
        <div class="advice-block">
            <div class="eyebrow">Embasamento — teste cego${sz.evaluated_at
                ? ` de ${esc(sz.evaluated_at.slice(5, 16))}` : ""}${sz.episodes
                ? ` · ${sz.episodes} episódios de treino` : ""}</div>
            <div class="metrics" style="margin-top:8px">
                <div class="metric"><div class="k">Robô</div>
                    <div class="v ${signClass(m.total_return_pct)}">${pct(m.total_return_pct, 1)}</div></div>
                <div class="metric"><div class="k">Buy &amp; Hold</div>
                    <div class="v ${signClass(m.benchmark_return_pct)}">${pct(m.benchmark_return_pct, 1)}</div></div>
                <div class="metric"><div class="k">Drawdown</div>
                    <div class="v neg">${pct(m.max_drawdown_pct, 1)}</div></div>
                <div class="metric"><div class="k">Sharpe</div>
                    <div class="v">${Number(m.sharpe_ratio).toFixed(2)}</div></div>
            </div>
            <div class="metrics" style="margin-top:6px">
                <div class="metric"><div class="k">Operações</div><div class="v">${m.total_trades}</div></div>
                <div class="metric"><div class="k">Acerto</div><div class="v">${Number(m.win_rate_pct).toFixed(0)}%</div></div>
                <div class="metric"><div class="k">Ganho médio</div>
                    <div class="v pos">${pct(m.avg_win_pct, 1)}</div></div>
                <div class="metric"><div class="k">Perda média</div>
                    <div class="v ${m.avg_loss_pct ? "neg" : "faint"}">${m.avg_loss_pct ? pct(m.avg_loss_pct, 1) : "nenhuma"}</div></div>
            </div>
        </div>` : "";

    const ajuste = sz.quality_reasons.length ? `
        <div class="advice-block">
            <div class="eyebrow">Por que o corte de ×${sz.quality_factor.toFixed(2)}</div>
            <ul class="advice-list">${sz.quality_reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
        </div>` : "";

    $("#run-advice").innerHTML = `
        <div class="advice">
            <div class="advice-head">
                <span class="eyebrow">Tamanho recomendado</span>
                <span class="advice-size">${size}</span>
            </div>

            <div class="advice-block">
                <div class="eyebrow">Como esse número saiu</div>
                <ul class="advice-list">${sz.steps.map((step) => `<li>${esc(step)}</li>`).join("")}</ul>
            </div>
            ${ajuste}
            ${evidencia}
            ${sz.warnings.map((w) => note("warn", esc(w))).join("")}

            <p class="advice-foot">Conta de risco feita sobre o backtest do seu próprio modelo:
                arrisca ${sz.risk_pct.toFixed(0)}% do patrimônio por operação, dividido pela perda que esse
                modelo teve no teste cego. Não é recomendação de investimento, e resultado de backtest
                não garante resultado futuro.</p>
        </div>`;
}

function updateRunWarning() {
    const mode = $("#run-mode").value;
    const box = $("#run-warning");
    if (REAL_MODES.includes(mode)) {
        box.innerHTML = note("risk", `Este modo envia ordem com <strong>dinheiro real</strong>
            ${mode === "mt5" ? "no MetaTrader 5" : "na conta real da Binance"}. Exige a trava liberada em Configurações.`);
    } else if (mode === "binance_testnet") {
        box.innerHTML = note("warn", "Ordem enviada à Binance Testnet, com dinheiro fictício.");
    } else {
        box.innerHTML = "";
    }
}

async function runCycle() {
    const btn = $("#btn-run-confirm");
    const input = $("#run-qty");
    const closing = State.run.closing;
    const body = { mode: $("#run-mode").value };

    if (closing) body.force_action = 2;

    if (input) {
        const value = parseFloat(input.value);
        if (!(value > 0)) return toast("Informe um tamanho de ordem maior que zero.", "error");
        body.quantity = value;
    }

    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> ${closing ? "Encerrando" : "Executando"}`;
    try {
        const r = (await api(`/api/assets/${encodeURIComponent(State.run.ticker)}/run`, {
            method: "POST", body,
        })).result;
        $("#run-result").innerHTML = note(r.executed ? "good" : "", esc(r.message));
        toast(r.message, r.executed ? "success" : "info", 6500);
        loadOverview();
    } catch (err) {
        $("#run-result").innerHTML = note("risk", esc(err.message));
        toast(err.message, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = closing
            ? `${icon("sell", 14)} Encerrar posição`
            : `${icon("play", 14)} Executar ciclo`;
    }
}

/* ------------------------------- Ações ---------------------------------- */
function findAsset(ticker) {
    const o = State.overview;
    if (!o) return null;
    return [...o.stocks, ...o.crypto].find((a) => a.ticker === ticker) || null;
}

async function handleCardAction(action, ticker) {
    const asset = findAsset(ticker);
    if (!asset) return;

    if (action === "run") return openRunModal(asset);
    if (action === "close") return openRunModal(asset, { close: true });
    if (action === "train") return openTrainModal(asset);
    if (action === "edit") return openAssetModal(asset.asset_class, asset);
    if (action === "report") {
        $("#report-title").textContent = `Backtest — ${ticker}`;
        $("#report-img").src = `/reports/${ticker.replace(".SA", "").replace(/-/g, "_")}_backtest_report.png?t=${Date.now()}`;
        return openModal("modal-report");
    }
    if (action === "delete") {
        if (!confirm(`Remover ${ticker} do catálogo?\n\nO modelo treinado e o relatório continuam salvos em disco.`)) return;
        try {
            await api(`/api/assets/${encodeURIComponent(ticker)}`, { method: "DELETE" });
            toast(`${ticker} removido.`, "success");
            loadOverview();
        } catch (err) {
            toast(err.message, "error");
        }
    }
}

async function patchAutomation(ticker, patch, revert) {
    try {
        await api(`/api/assets/${encodeURIComponent(ticker)}/automation`, { method: "PUT", body: patch });
        loadOverview();
    } catch (err) {
        toast(err.message, "error");
        if (revert) revert();
    }
}

/* ------------------------------ Conexões -------------------------------- */
async function testConnection(kind, real = false) {
    const target = kind === "mt5" ? $("#mt5-result") : $("#binance-result");
    target.innerHTML = '<span class="spinner"></span>';
    try {
        const info = (await api(`/api/connections?binance=${real ? "real" : "testnet"}`))[kind];
        if (kind === "mt5") {
            target.innerHTML = info.connected
                ? note("good", `Conta <strong>${esc(String(info.login))}</strong> · ${esc(info.server)} ·
                     ${info.demo ? "demo" : "real"}<br>
                     Saldo ${money(info.balance)} · Patrimônio ${money(info.equity)}`)
                : note("risk", esc(info.message));
        } else {
            const balances = info.balances
                ? Object.entries(info.balances).map(([k, v]) => `${k} ${qty(v)}`).join(" · ")
                : "";
            target.innerHTML = info.connected
                ? note("good", `${esc(info.message)}<br><span class="figure">${esc(balances)}</span>`)
                : note("risk", esc(info.message));
        }
    } catch (err) {
        target.innerHTML = note("risk", esc(err.message));
    }
}

/* ------------------------------ Eventos --------------------------------- */
function bindEvents() {
    // Abas
    $$(".tab").forEach((tab) => tab.addEventListener("click", () => {
        $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
        State.view = tab.dataset.view;
        $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${State.view}`));
        window.scrollTo({ top: 0 });  // sem isso a aba nova abre rolada pela lista anterior
    }));

    // Fechar modais
    document.addEventListener("click", (ev) => {
        if (ev.target.closest("[data-close]") || ev.target.classList.contains("modal-backdrop")) {
            const backdrop = ev.target.closest(".modal-backdrop");
            if (backdrop) {
                backdrop.classList.remove("open");
                if (backdrop.id === "modal-train") clearInterval(State.train.timer);
            }
        }
    });
    document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") $$(".modal-backdrop.open").forEach((m) => m.classList.remove("open"));
    });

    // Botões dos cards e da tabela (delegação)
    document.addEventListener("click", (ev) => {
        const btn = ev.target.closest("[data-act]");
        if (btn && !btn.disabled) handleCardAction(btn.dataset.act, btn.dataset.ticker);

        const add = ev.target.closest("[data-add-asset]");
        if (add) openAssetModal(add.dataset.addAsset);

        const wallet = ev.target.closest("[data-wallet]");
        if (wallet) handleWalletAction(wallet.dataset.wallet, wallet.dataset.currency);
    });

    // Automação por ativo
    document.addEventListener("change", (ev) => {
        const el = ev.target.closest("[data-auto]");
        if (!el) return;
        const ticker = el.dataset.ticker;
        if (el.dataset.auto === "enabled") {
            patchAutomation(ticker, { enabled: el.checked }, () => { el.checked = !el.checked; });
        } else if (el.dataset.auto === "mode") {
            patchAutomation(ticker, { mode: el.value });
        } else if (el.dataset.auto === "interval") {
            patchAutomation(ticker, { interval_minutes: parseInt(el.value, 10) });
        }
    });

    // Topbar
    $("#btn-refresh").addEventListener("click", () => loadOverview(true));
    $("#master-switch").addEventListener("change", async (ev) => {
        try {
            await api("/api/automation/master", { method: "POST", body: { enabled: ev.target.checked } });
            toast(ev.target.checked ? "Automação geral ligada." : "Automação geral desligada.",
                ev.target.checked ? "warning" : "info");
            loadOverview();
        } catch (err) {
            toast(err.message, "error");
            ev.target.checked = !ev.target.checked;
        }
    });
    $("#btn-panic").addEventListener("click", async () => {
        if (!confirm("Desligar a automação de TODOS os ativos agora?")) return;
        try {
            await api("/api/automation/panic", { method: "POST" });
            toast("Automação totalmente desligada.", "warning");
            loadOverview();
        } catch (err) {
            toast(err.message, "error");
        }
    });

    // Modal de ativo
    $("#af-class").addEventListener("change", updateAssetHint);
    $("#btn-save-asset").addEventListener("click", saveAsset);

    // Modal de treino
    $("#btn-train-start").addEventListener("click", startTraining);
    $("#btn-train-cancel").addEventListener("click", async () => {
        try {
            await api(`/api/jobs/${State.train.jobId}/cancel`, { method: "POST" });
            toast("Cancelamento solicitado — o treino para no fim do episódio atual.", "warning");
        } catch (err) {
            toast(err.message, "error");
        }
    });

    // Modal de execução
    $("#btn-run-confirm").addEventListener("click", runCycle);

    // Configurações
    $("#btn-save-binance").addEventListener("click", async () => {
        try {
            await api("/api/settings", {
                method: "POST",
                body: {
                    binance_api_key: $("#cfg-binance-key").value.trim(),
                    binance_secret_key: $("#cfg-binance-secret").value.trim(),
                },
            });
            $("#cfg-binance-key").value = "";
            $("#cfg-binance-secret").value = "";
            toast("Chaves da Binance salvas.", "success");
            loadOverview();
        } catch (err) {
            toast(err.message, "error");
        }
    });
    $("#btn-clear-binance").addEventListener("click", async () => {
        if (!confirm("Apagar as chaves da Binance salvas neste computador?")) return;
        await api("/api/settings", { method: "POST", body: { clear_binance_keys: true } });
        toast("Chaves removidas.", "warning");
        loadOverview();
    });
    $("#btn-test-binance").addEventListener("click", () => testConnection("binance", false));
    $("#btn-test-binance-real").addEventListener("click", () => testConnection("binance", true));
    $("#btn-test-mt5").addEventListener("click", () => testConnection("mt5"));

    $("#cfg-real-money").addEventListener("change", async (ev) => {
        if (ev.target.checked && !confirm(
            "Liberar o envio de ordens com DINHEIRO REAL?\n\n" +
            "O robô poderá comprar e vender sozinho na sua conta do MetaTrader 5 e na conta real da Binance.")) {
            ev.target.checked = false;
            return;
        }
        await api("/api/settings", { method: "POST", body: { allow_real_money: ev.target.checked } });
        toast(ev.target.checked ? "Trava liberada — ordens reais permitidas." : "Trava de dinheiro real ativada.",
            ev.target.checked ? "warning" : "success");
        loadOverview();
    });
    $("#btn-save-cache").addEventListener("click", async () => {
        await api("/api/settings", { method: "POST", body: { quote_cache_minutes: parseInt($("#cfg-cache").value, 10) } });
        toast("Configuração salva.", "success");
    });
}

async function handleWalletAction(action, currency) {
    if (action === "deposit") {
        const value = prompt(`Valor do aporte em ${currency}:`, currency === "USDT" ? "500" : "5000");
        if (!value) return;
        try {
            await api(`/api/portfolio/${currency}/deposit`, { method: "POST", body: { amount: parseFloat(value) } });
            toast("Aporte registrado.", "success");
            loadOverview();
        } catch (err) {
            toast(err.message, "error");
        }
    } else if (action === "reset") {
        const value = prompt(
            `Reiniciar a carteira ${currency}?\n\nIsso apaga posições e histórico dessa conta.\nSaldo inicial:`,
            currency === "USDT" ? "1000" : "10000");
        if (!value) return;
        try {
            await api(`/api/portfolio/${currency}/reset`, { method: "POST", body: { initial_cash: parseFloat(value) } });
            toast(`Carteira ${currency} reiniciada.`, "warning");
            loadOverview();
        } catch (err) {
            toast(err.message, "error");
        }
    }
}

/* ------------------------------- Início ---------------------------------- */
hydrateIcons();
bindEvents();
loadOverview();
setInterval(() => {
    if (!document.querySelector(".modal-backdrop.open")) loadOverview();
}, 30000);
