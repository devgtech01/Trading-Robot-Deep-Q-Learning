/* ==========================================================================
 *  icons.js - Conjunto de ícones SVG traçados do painel.
 *
 *  Grade de 24px, traço de 1.75, pontas arredondadas, cor herdada do texto
 *  (currentColor). Nenhum emoji na interface: os ícones escalam, recolorem
 *  e mantêm o mesmo peso visual em qualquer tamanho.
 * ========================================================================== */

(function (global) {
    "use strict";

    const P = {
        /* Navegação */
        equities: '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
        crypto: '<circle cx="9" cy="9" r="6.5"/><path d="M18.1 10.4A6.5 6.5 0 1 1 10.3 18.1"/><path d="M8 6.6h1.1v4.8"/><path d="M15.4 14.1l.8.8-2.9 2.9"/>',
        wallet: '<path d="M19 7V5a1 1 0 0 0-1-1H5.5A2.5 2.5 0 0 0 3 6.5v11A2.5 2.5 0 0 0 5.5 20H19a1 1 0 0 0 1-1v-2"/><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4"/><path d="M20 10.5h-4a1.5 1.5 0 0 0 0 3h4a1 1 0 0 0 1-1v-1a1 1 0 0 0-1-1Z"/>',
        automation: '<path d="M4 21v-6"/><path d="M4 11V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-4"/><path d="M20 13V3"/><path d="M1.5 15h5"/><path d="M9.5 8h5"/><path d="M17.5 17h5"/>',
        history: '<path d="M3 3.5v5h5"/><path d="M3.3 13a9 9 0 1 0 2.4-7.2L3 8.5"/><path d="M12 7.5V12l3.5 2"/>',
        shield: '<path d="M20 12.6c0 4.8-3.4 7.3-7.5 8.7a1 1 0 0 1-.7 0C7.5 19.9 4 17.4 4 12.6V6a1 1 0 0 1 1-1c2 0 4.4-1.2 6.1-2.7a1.1 1.1 0 0 1 1.5 0C14.4 3.8 16.9 5 19 5a1 1 0 0 1 1 1Z"/>',

        /* Ações */
        refresh: '<path d="M3.5 12a8.5 8.5 0 0 1 14.4-6.1L21 8.8"/><path d="M21 4v5h-5"/><path d="M20.5 12a8.5 8.5 0 0 1-14.4 6.1L3 15.2"/><path d="M3 20v-5h5"/>',
        power: '<path d="M12 3v9"/><path d="M18.4 6.8a9 9 0 1 1-12.8 0"/>',
        plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
        play: '<path d="M7 4.5v15l12-7.5Z"/>',
        train: '<rect x="4.5" y="4.5" width="15" height="15" rx="2.5"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v2.5"/><path d="M15 2v2.5"/><path d="M9 19.5V22"/><path d="M15 19.5V22"/><path d="M2 9h2.5"/><path d="M2 15h2.5"/><path d="M19.5 9H22"/><path d="M19.5 15H22"/>',
        chart: '<path d="M3.5 3v17.5H21"/><path d="M18 16.5V9"/><path d="M13 16.5V5.5"/><path d="M8 16.5v-4"/>',
        edit: '<path d="M12 20.5h9"/><path d="m16.4 3.6 4 4L7.6 20.4l-4.6 1 1-4.6Z"/>',
        trash: '<path d="M3.5 6h17"/><path d="M8.5 6V4.5a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1V6"/><path d="M18.5 6v13a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2V6"/><path d="M10 10.5v6"/><path d="M14 10.5v6"/>',
        close: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',

        /* Sinais */
        buy: '<path d="M12 19V5"/><path d="m5.5 11.5 6.5-6.5 6.5 6.5"/>',
        sell: '<path d="M12 5v14"/><path d="m5.5 12.5 6.5 6.5 6.5-6.5"/>',
        hold: '<path d="M5 12h14"/>',

        /* Estados */
        check: '<path d="M20 6.5 9.5 17 4 11.5"/>',
        alert: '<path d="M12 3.5 21.5 20H2.5Z"/><path d="M12 10v4"/><path d="M12 17.2v.1"/>',
        info: '<circle cx="12" cy="12" r="9"/><path d="M12 11.5V16"/><path d="M12 8.3v.1"/>',
        lock: '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>',
        unlock: '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 7.7-1.5"/>',
        pulse: '<path d="M22 12h-4l-3 8.5L9 3.5l-3 8.5H2"/>',

        /* Corretoras e configurações */
        key: '<circle cx="16.5" cy="7.5" r="4.5"/><path d="m13.3 10.7-9.4 9.4a1 1 0 0 0-.3.7V22h1.9a1 1 0 0 0 .7-.3l1.3-1.3v-2h2v-2h2l1.8-1.8"/>',
        terminal: '<rect x="2.5" y="4" width="19" height="16" rx="2"/><path d="m7 9.5 3 2.5-3 2.5"/><path d="M13 15h4"/>',
        clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
        link: '<path d="M9.5 14.5 14.5 9.5"/><path d="M11 6.5 12.8 4.7a4.5 4.5 0 0 1 6.5 6.5L17.5 13"/><path d="M13 17.5l-1.8 1.8a4.5 4.5 0 0 1-6.5-6.5L6.5 11"/>',
    };

    /** Devolve o markup de um ícone. `size` em px, qualquer valor. */
    function icon(name, size = 16, extraClass = "") {
        const path = P[name];
        if (!path) return "";
        const px = Number(size) || 16;
        // O tamanho vai inline: assim nenhum ícone depende de uma classe .i-N existir.
        return `<span class="i ${extraClass}" style="width:${px}px;height:${px}px" aria-hidden="true">` +
            `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" ` +
            `stroke-linecap="round" stroke-linejoin="round">${path}</svg></span>`;
    }

    /** Preenche todo `<i data-icon="nome" data-size="16">` ainda vazio. */
    function hydrateIcons(root = document) {
        root.querySelectorAll("[data-icon]").forEach((el) => {
            if (el.dataset.iconDone === "1") return;
            const markup = icon(el.dataset.icon, el.dataset.size || 16);
            if (!markup) return;
            el.outerHTML = markup;
        });
    }

    global.icon = icon;
    global.hydrateIcons = hydrateIcons;
    global.ICON_NAMES = Object.keys(P);
})(window);
