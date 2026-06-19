// static/js/main.js — DocVault: Scripts de interfaz

// ── Auto-cerrar mensajes flash después de 5 segundos ────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash").forEach(el => {
    setTimeout(() => el.remove(), 5000);
  });

  // ── Activar enlace de navegación actual ──────────────────────────────────
  const path = window.location.pathname;
  document.querySelectorAll(".nav-link").forEach(link => {
    if (link.getAttribute("href") === path) link.classList.add("active");
  });

  // ── Confirmar eliminación con Enter/Space en botones de teclado ──────────
  document.querySelectorAll(".btn-delete").forEach(btn => {
    btn.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") btn.click();
    });
  });

  // ── Resaltar fila de tabla al hacer click ─────────────────────────────────
  document.querySelectorAll(".doc-row").forEach(row => {
    row.addEventListener("click", e => {
      if (e.target.closest(".actions-cell")) return;
      const link = row.querySelector(".doc-link");
      if (link) link.click();
    });
    row.style.cursor = "pointer";
  });
});

// ── Búsqueda con debounce (500ms) ────────────────────────────────────────────
const searchInput = document.querySelector(".search-input");
if (searchInput) {
  let debounceTimer;
  searchInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    // Sólo auto-envía si el campo se vacía (limpiar búsqueda)
    if (searchInput.value === "") {
      debounceTimer = setTimeout(() => searchInput.closest("form").submit(), 400);
    }
  });
}
