/* Avisos em tempo real: consulta /api/notificacoes a cada 8 s e mostra um alerta na tela
   (ex.: "💰 Pagamento recebido") para o usuário logado. */
(function () {
  "use strict";
  if (!window.FC || !window.FC.apiNotif) return;
  let ultimo = null;
  const caixa = document.getElementById("toasts");

  function esc(t) { const d = document.createElement("div"); d.textContent = t || ""; return d.innerHTML; }

  function toast(n) {
    if (!caixa) return;
    const el = document.createElement(n.link ? "a" : "div");
    el.className = "toast-aviso " + (n.tipo || "");
    if (n.link) el.href = n.link;
    el.innerHTML = `<b>${esc(n.titulo)}</b>${n.mensagem ? `<span>${esc(n.mensagem)}</span>` : ""}`;
    caixa.appendChild(el);
    setTimeout(() => el.classList.add("sai"), 9000);
    setTimeout(() => el.remove(), 9600);
    if (n.tipo === "pagamento") tocar();
    document.dispatchEvent(new CustomEvent("fc:notificacao", { detail: n }));
  }

  function tocar() {   // bip curto ao receber pagamento (navegadores só tocam após alguma interação)
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = 880; g.gain.value = 0.06; o.connect(g); g.connect(ctx.destination);
      o.start(); o.stop(ctx.currentTime + 0.18);
    } catch (e) {}
  }

  async function checar() {
    try {
      const r = await fetch(window.FC.apiNotif + (ultimo !== null ? "?desde=" + ultimo : ""), { headers: { "Accept": "application/json" } });
      if (!r.ok) return;
      const j = await r.json();
      if (ultimo !== null) j.novas.forEach(toast);
      ultimo = j.ultimo;
      document.querySelectorAll("[data-notif-badge]").forEach(b => { b.textContent = j.nao_lidas; b.hidden = !j.nao_lidas; });
    } catch (e) {}
  }
  checar();
  setInterval(checar, 8000);
  window.FC.checarAvisos = checar;
})();
