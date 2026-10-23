/* FeiraConnect — comportamento da loja (sem frameworks) */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  const ler = (k, padrao) => { try { return JSON.parse(localStorage.getItem(k)) ?? padrao; } catch (e) { return padrao; } };

  /* ---------- contador até o fim das promoções do dia (meia-noite) ---------- */
  function atualizarContadores() {
    const agora = new Date(), fim = new Date(agora);
    fim.setHours(23, 59, 59, 999);
    const s = Math.max(0, Math.floor((fim - agora) / 1000));
    const txt = [Math.floor(s / 3600), Math.floor(s % 3600 / 60), s % 60].map(n => String(n).padStart(2, "0")).join(":");
    $$("[data-contador]").forEach(el => el.textContent = txt);
  }
  atualizarContadores(); setInterval(atualizarContadores, 1000);

  /* ---------- acessibilidade: tamanho da letra e alto contraste ---------- */
  const a11y = ler("fc_a11y", {});
  $$("[data-fonte]").forEach(b => b.addEventListener("click", () => {
    a11y.fonte = Math.min(22, Math.max(13, (a11y.fonte || 16) + Number(b.dataset.fonte)));
    document.documentElement.style.fontSize = a11y.fonte + "px"; guardar("fc_a11y", a11y);
  }));
  $$("[data-contraste]").forEach(b => b.addEventListener("click", () => {
    a11y.contraste = !a11y.contraste;
    document.documentElement.classList.toggle("alto-contraste", a11y.contraste); guardar("fc_a11y", a11y);
  }));

  /* ---------- modais ---------- */
  function abrir(m) { m.classList.add("aberto"); const f = $("button, a, input", m); f && f.focus(); }
  function fechar(m) { m.classList.remove("aberto"); }
  $$(".modal").forEach(m => {
    m.addEventListener("click", e => { if (e.target === m || e.target.closest("[data-fechar]")) fechar(m); });
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") $$(".modal.aberto").forEach(fechar); });
  const modalGps = $("#modal-gps");
  $$("[data-abrir-gps]").forEach(b => b.addEventListener("click", () => {
    const promo = $("#modal-promo"); promo && fechar(promo);
    abrir(modalGps);
  }));

  /* ---------- GPS: coordenadas -> endereço completo (OpenStreetMap / Nominatim) ---------- */
  const statusGps = $("[data-gps-status]");
  function mostrarStatus(html, ok) { if (statusGps) { statusGps.innerHTML = html; statusGps.classList.toggle("ok", !!ok); } }

  function montarEndereco(a, displayName) {
    if (!a) return { completo: displayName || "", curto: "" };
    const rua = a.road || a.pedestrian || a.footway || a.street || "";
    const numero = a.house_number ? ", " + a.house_number : "";
    const bairro = a.suburb || a.neighbourhood || a.quarter || a.city_district || "";
    const cidade = a.city || a.town || a.village || a.municipality || "";
    const uf = (a["ISO3166-2-lvl4"] || "").replace("BR-", "") || a.state || "";
    const cep = a.postcode ? " - CEP " + a.postcode : "";
    const partes = [rua + numero, bairro, cidade && uf ? cidade + " - " + uf : cidade || uf].filter(Boolean);
    return { completo: (partes.join(", ") + cep) || displayName, curto: (rua + numero) || bairro || cidade };
  }

  async function enderecoDeCoordenadas(lat, lng) {
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&addressdetails=1&accept-language=pt-BR&lat=${lat}&lon=${lng}`);
      const j = await r.json();
      return montarEndereco(j.address, j.display_name);
    } catch (e) {
      return { completo: `Lat ${lat.toFixed(5)}, Long ${lng.toFixed(5)}`, curto: "Minha localização" };
    }
  }

  async function salvarLocal(lat, lng, end) {
    const r = await fetch(window.FC.apiLocal, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": window.FC.csrf },
      body: JSON.stringify({ lat, lng, endereco: end.completo, curto: end.curto }),
    });
    return r.ok;
  }

  async function aposLocalizar(lat, lng, end) {
    mostrarStatus(`<b>📍 Endereço encontrado:</b><br>${end.completo}<br><small>Atualizando promoções e fretes perto de você...</small>`, true);
    await salvarLocal(lat, lng, end);
    document.dispatchEvent(new CustomEvent("fc:local", { detail: { lat, lng, endereco: end.completo } }));
    if (!document.body.dataset.semRecarregar) setTimeout(() => location.reload(), 900);
  }

  function usarGps() {
    if (!("geolocation" in navigator)) { mostrarStatus("Seu navegador não tem suporte a GPS. Digite o endereço abaixo."); return; }
    mostrarStatus("<span class='pulse'></span> Procurando sua localização pelo GPS…");
    navigator.geolocation.getCurrentPosition(async pos => {
      const { latitude: lat, longitude: lng, accuracy } = pos.coords;
      mostrarStatus(`<span class='pulse'></span> Localização encontrada (precisão ~${Math.round(accuracy)} m). Buscando o endereço completo…`);
      aposLocalizar(lat, lng, await enderecoDeCoordenadas(lat, lng));
    }, err => {
      const msg = { 1: "Permissão negada. Libere a localização no navegador ou digite o endereço.", 2: "Não foi possível obter o sinal do GPS.", 3: "O GPS demorou para responder. Tente novamente." }[err.code] || "Erro ao obter localização.";
      mostrarStatus(msg);
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  }
  $$("[data-usar-gps]").forEach(b => b.addEventListener("click", usarGps));
  window.FC.usarGps = usarGps;

  const formManual = $("[data-endereco-manual]");
  formManual && formManual.addEventListener("submit", async e => {
    e.preventDefault();
    const q = $("input", formManual).value.trim();
    if (!q) return;
    mostrarStatus("<span class='pulse'></span> Procurando endereço…");
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&limit=1&countrycodes=br&accept-language=pt-BR&q=${encodeURIComponent(q)}`);
      const [res] = await r.json();
      if (!res) { mostrarStatus("Endereço não encontrado. Tente incluir bairro e cidade."); return; }
      const end = montarEndereco(res.address, res.display_name);
      aposLocalizar(Number(res.lat), Number(res.lon), end);
    } catch (err) { mostrarStatus("Sem conexão para buscar o endereço agora."); }
  });

  /* ---------- aviso de promoções do dia (aparece 1x por dia) ---------- */
  const modalPromo = $("#modal-promo");
  if (modalPromo) {
    const hoje = new Date().toISOString().slice(0, 10);
    if (ler("fc_promo_visto") !== hoje) setTimeout(() => abrir(modalPromo), 900);
    modalPromo.addEventListener("click", e => { if (e.target === modalPromo || e.target.closest("[data-fechar]")) guardar("fc_promo_visto", hoje); });
  }

  /* ---------- carrossel do banner ---------- */
  const hero = $(".hero");
  if (hero) {
    const trilho = $(".slides", hero), dots = $$(".dots button", hero); let i = 0;
    const ir = n => { i = (n + dots.length) % dots.length; trilho.style.transform = `translateX(-${i * 100}%)`; dots.forEach((d, k) => d.classList.toggle("ativo", k === i)); };
    dots.forEach((d, k) => d.addEventListener("click", () => ir(k)));
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) setInterval(() => ir(i + 1), 6000);
  }

  /* ---------- seletor de quantidade ---------- */
  $$(".qtd-ctrl").forEach(box => {
    const inp = $("input", box), max = Number(inp.max || 999), min = Number(inp.min || 1);
    $$("button", box).forEach(b => b.addEventListener("click", () => {
      inp.value = Math.min(max, Math.max(min, Number(inp.value || 1) + Number(b.dataset.passo)));
      inp.dispatchEvent(new Event("change", { bubbles: true }));
    }));
  });
  $$("[data-auto-submit]").forEach(inp => inp.addEventListener("change", () => inp.form.submit()));

  /* ---------- copiar PIX ---------- */
  $$("[data-copiar]").forEach(b => b.addEventListener("click", async () => {
    const alvo = $(b.dataset.copiar); alvo.select();
    try { await navigator.clipboard.writeText(alvo.value); } catch (e) { document.execCommand("copy"); }
    const t = b.textContent; b.textContent = "Copiado!"; setTimeout(() => b.textContent = t, 1800);
  }));
})();
