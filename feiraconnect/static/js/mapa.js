/* Mapas (Leaflet + OpenStreetMap): banca do feirante, cliente e escolha de ponto no admin */
(function () {
  if (!window.L) return;
  const pino = (cor) => L.divIcon({
    className: "", iconSize: [30, 40], iconAnchor: [15, 38],
    html: `<svg width="30" height="40" viewBox="0 0 30 40"><path d="M15 39s13-12.4 13-23A13 13 0 0 0 2 16c0 10.6 13 23 13 23z" fill="${cor}" stroke="#fff" stroke-width="2"/><circle cx="15" cy="16" r="5" fill="#fff"/></svg>`,
  });

  document.querySelectorAll(".mapa").forEach(el => {
    const lat = parseFloat(el.dataset.lat), lng = parseFloat(el.dataset.lng);
    const centro = isNaN(lat) ? [-3.1316, -60.0233] : [lat, lng];
    const mapa = L.map(el, { scrollWheelZoom: false }).setView(centro, 14);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap",
    }).addTo(mapa);

    let banca = null;
    if (!isNaN(lat)) banca = L.marker(centro, { icon: pino("#2E7D32") }).addTo(mapa).bindPopup(el.dataset.nome || "Banca");

    const clat = parseFloat(el.dataset.clat), clng = parseFloat(el.dataset.clng);
    if (!isNaN(clat) && banca) {
      const cliente = L.marker([clat, clng], { icon: pino("#C2692B") }).addTo(mapa).bindPopup("Você está aqui");
      L.polyline([centro, [clat, clng]], { color: "#8D5B3A", dashArray: "6 8", weight: 3 }).addTo(mapa);
      mapa.fitBounds(L.latLngBounds([centro, [clat, clng]]).pad(0.25));
    }

    // Admin: clicar no mapa define a posição da banca
    if (el.dataset.editavel !== undefined) {
      const inLat = document.querySelector(el.dataset.inputLat), inLng = document.querySelector(el.dataset.inputLng);
      const mover = (ll) => {
        if (!banca) banca = L.marker(ll, { icon: pino("#2E7D32") }).addTo(mapa); else banca.setLatLng(ll);
        inLat.value = ll.lat.toFixed(6); inLng.value = ll.lng.toFixed(6);
      };
      mapa.on("click", e => mover(e.latlng));
      document.addEventListener("fc:posicao", e => { mover(L.latLng(e.detail.lat, e.detail.lng)); mapa.setView([e.detail.lat, e.detail.lng], 16); });
    }
    setTimeout(() => mapa.invalidateSize(), 200);
  });
})();
