/* Formulários de cadastro: máscaras, prévia da foto, busca do endereço pelo CEP (ViaCEP)
   e marcação da posição pelo GPS. */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const dig = v => (v || "").replace(/\D/g, "");

  const mascaras = {
    cpf: d => d.slice(0, 11).replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2"),
    cpfcnpj: d => d.length <= 11 ? mascaras.cpf(d) :
      d.slice(0, 14).replace(/^(\d{2})(\d)/, "$1.$2").replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3").replace(/\.(\d{3})(\d)/, ".$1/$2").replace(/(\d{4})(\d{1,2})$/, "$1-$2"),
    celular: d => d.slice(0, 11).replace(/^(\d{2})(\d)/, "($1) $2").replace(/(\d{5})(\d{1,4})$/, "$1-$2"),
    cep: d => d.slice(0, 8).replace(/^(\d{5})(\d)/, "$1-$2"),
    cartao: d => d.slice(0, 19).replace(/(.{4})/g, "$1 ").trim(),
    validade: d => d.slice(0, 4).replace(/^(\d{2})(\d)/, "$1/$2"),
  };
  document.querySelectorAll("[data-mascara]").forEach(inp => {
    const f = mascaras[inp.dataset.mascara];
    inp.addEventListener("input", () => { inp.value = f(dig(inp.value)); });
    if (inp.value) inp.value = f(dig(inp.value));
  });

  // Bandeira do cartão (Visa, Mastercard, Elo)
  const num = $("#cartao_numero"), band = $("[data-bandeira]");
  if (num && band) num.addEventListener("input", () => {
    const d = dig(num.value);
    band.textContent = /^(4011|4312|4389|4514|4576|5041|5066|5067|509|6277|6362|6363|650|6516|6550)/.test(d) ? "Elo"
      : /^4/.test(d) ? "Visa" : /^(5[1-5]|2[2-7])/.test(d) ? "Mastercard" : (d.length > 5 ? "Bandeira não aceita (só Visa, Mastercard e Elo)" : "");
  });

  // Contador do login (máx. 10)
  document.querySelectorAll("[data-contador-max]").forEach(inp => {
    const span = inp.parentElement.querySelector("[data-contagem]");
    const at = () => { inp.value = inp.value.toLowerCase().replace(/[^a-z0-9._]/g, "").slice(0, 10); if (span) span.textContent = inp.value.length; };
    inp.addEventListener("input", at); at();
  });

  // Prévia da foto
  document.querySelectorAll("[data-foto]").forEach(inp => inp.addEventListener("change", () => {
    const f = inp.files[0], img = $("[data-preview-foto]");
    if (f && img) { img.src = URL.createObjectURL(f); img.parentElement.classList.add("tem-foto"); }
  }));

  // CEP -> endereço (ViaCEP)
  const cep = $("[data-buscar-cep]"), st = $("[data-cep-status]");
  if (cep) cep.addEventListener("input", async () => {
    const d = dig(cep.value);
    if (d.length !== 8) return;
    if (st) st.textContent = "Buscando endereço…";
    try {
      const j = await (await fetch(`https://viacep.com.br/ws/${d}/json/`)).json();
      if (j.erro) { if (st) st.textContent = "CEP não encontrado. Preencha manualmente."; return; }
      const set = (id, v) => { const el = $("#" + id); if (el && v && !el.value) el.value = v; };
      set("logradouro", j.logradouro); set("bairro", j.bairro); set("cidade", j.localidade); set("uf", j.uf);
      const uf = $("#uf"); if (uf && j.uf) uf.value = j.uf;
      if (st) st.textContent = "Endereço encontrado. Confira e informe o número.";
      $("#numero") && $("#numero").focus();
    } catch (e) { if (st) st.textContent = "Sem conexão com a busca de CEP. Preencha manualmente."; }
  });

  // GPS -> lat/lng (e preenche o endereço se estiver vazio)
  const bGps = $("[data-gps-cadastro]"), stGps = $("[data-gps-cadastro-status]");
  if (bGps) bGps.addEventListener("click", () => {
    if (!navigator.geolocation) { stGps.textContent = "Este navegador não tem GPS."; return; }
    stGps.textContent = "Procurando sua posição…";
    navigator.geolocation.getCurrentPosition(async p => {
      $("#lat").value = p.coords.latitude.toFixed(6); $("#lng").value = p.coords.longitude.toFixed(6);
      stGps.textContent = `Posição marcada (precisão ~${Math.round(p.coords.accuracy)} m).`;
      document.dispatchEvent(new CustomEvent("fc:posicao", { detail: { lat: p.coords.latitude, lng: p.coords.longitude } }));
      try {
        const j = await (await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&accept-language=pt-BR&lat=${p.coords.latitude}&lon=${p.coords.longitude}`)).json();
        const a = j.address || {}, set = (id, v) => { const el = $("#" + id); if (el && v && !el.value) el.value = v; };
        set("logradouro", a.road); set("numero", a.house_number); set("bairro", a.suburb || a.neighbourhood);
        set("cidade", a.city || a.town); set("cep", a.postcode);
      } catch (e) {}
    }, () => { stGps.textContent = "Não foi possível obter a posição. Verifique a permissão do navegador."; },
    { enableHighAccuracy: true, timeout: 15000 });
  });
})();
