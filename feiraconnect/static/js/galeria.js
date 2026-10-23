/* Galeria de fotos do produto: troca a foto principal e a legenda, setas do teclado e tela cheia. */
(function () {
  document.querySelectorAll("[data-galeria]").forEach(gal => {
    const img = gal.querySelector("[data-galeria-img]"), leg = gal.querySelector("[data-galeria-legenda]");
    const cont = gal.querySelector("[data-galeria-n]");
    const botoes = Array.from(gal.querySelectorAll(".galeria-miniaturas button"));
    let atual = 0;
    function ir(i) {
      if (!botoes.length) return;
      atual = (i + botoes.length) % botoes.length;
      const b = botoes[atual];
      img.src = b.dataset.src;
      leg.textContent = b.dataset.legenda || "";
      leg.hidden = !b.dataset.legenda;
      if (cont) cont.textContent = `${atual + 1} / ${botoes.length}`;
      botoes.forEach((x, k) => x.classList.toggle("ativa", k === atual));
    }
    botoes.forEach((b, k) => b.addEventListener("click", () => ir(k)));
    gal.addEventListener("keydown", e => { if (e.key === "ArrowRight") ir(atual + 1); if (e.key === "ArrowLeft") ir(atual - 1); });
    img.addEventListener("click", () => { if (img.requestFullscreen) img.requestFullscreen().catch(() => {}); });
    let x0 = null;   // deslizar no celular
    img.addEventListener("touchstart", e => x0 = e.touches[0].clientX, { passive: true });
    img.addEventListener("touchend", e => { if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 40) ir(atual + (dx < 0 ? 1 : -1)); x0 = null; });
  });
})();
