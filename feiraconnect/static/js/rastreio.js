/* Acompanhamento da entrega em tempo real (cliente e vendedor):
   busca as posições GPS enviadas pelo entregador a cada 5 s e desenha o trajeto no mapa. */
(function () {
  "use strict";
  const el = document.querySelector("[data-rastreio]");
  if (!el || !window.L) return;
  const pino = cor => L.divIcon({ className: "", iconSize: [28, 38], iconAnchor: [14, 36],
    html: `<svg width="28" height="38" viewBox="0 0 30 40"><path d="M15 39s13-12.4 13-23A13 13 0 0 0 2 16c0 10.6 13 23 13 23z" fill="${cor}" stroke="#fff" stroke-width="2"/><circle cx="15" cy="16" r="5" fill="#fff"/></svg>` });
  const moto = L.divIcon({ className: "", iconSize: [36, 36], iconAnchor: [18, 18],
    html: `<div class="entregador-ponto"><span></span></div>` });

  const o = [parseFloat(el.dataset.lat), parseFloat(el.dataset.lng)], d = [parseFloat(el.dataset.dlat), parseFloat(el.dataset.dlng)];
  const mapa = L.map(el, { scrollWheelZoom: false });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(mapa);
  const limites = [];
  if (!isNaN(o[0])) { L.marker(o, { icon: pino("#2E7D32") }).addTo(mapa).bindPopup("Banca"); limites.push(o); }
  if (!isNaN(d[0])) { L.marker(d, { icon: pino("#C2692B") }).addTo(mapa).bindPopup("Destino"); limites.push(d); }
  if (limites.length) mapa.fitBounds(L.latLngBounds(limites).pad(0.3)); else mapa.setView([-3.13, -60.02], 13);
  const trajeto = L.polyline([], { color: "#1F5C8A", weight: 4, opacity: .8 }).addTo(mapa);
  let marcador = null, ultimo = 0, seguir = true;
  mapa.on("dragstart", () => seguir = false);

  const status = document.querySelector("[data-rastreio-status]"), info = document.querySelector("[data-rastreio-info]");
  function distKm(a, b) {
    const r = 6371, dLat = (b[0] - a[0]) * Math.PI / 180, dLng = (b[1] - a[1]) * Math.PI / 180;
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * Math.PI / 180) * Math.cos(b[0] * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
    return 2 * r * Math.asin(Math.sqrt(x));
  }
  async function atualizar() {
    try {
      const j = await (await fetch(el.dataset.rastreio + "?desde=" + ultimo)).json();
      status.textContent = j.status_texto;
      j.pontos.forEach(p => { trajeto.addLatLng([p.lat, p.lng]); ultimo = p.id; });
      if (j.pontos.length) {
        const p = j.pontos[j.pontos.length - 1], pos = [p.lat, p.lng];
        if (!marcador) marcador = L.marker(pos, { icon: moto, zIndexOffset: 1000 }).addTo(mapa).bindPopup("Entregador");
        else marcador.setLatLng(pos);
        if (seguir) mapa.panTo(pos);
        const hora = p.criado_em.slice(11, 16);
        if (!isNaN(d[0])) {
          const km = distKm(pos, d) * 1.3, min = Math.max(1, Math.round(km / 25 * 60));
          info.textContent = j.status === "saiu_entrega" ? `Entregador a ${km.toFixed(1).replace(".", ",")} km · chega em ~${min} min · atualizado às ${hora}` : `Última posição às ${hora}`;
        }
      } else if (j.status === "entregue") info.textContent = "Pedido entregue.";
      if (["entregue", "cancelado"].includes(j.status)) clearInterval(timer);
    } catch (e) {}
  }
  atualizar();
  const timer = setInterval(atualizar, 5000);
  setTimeout(() => mapa.invalidateSize(), 200);
})();
