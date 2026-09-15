// Country filter for docs/carriers.md. Wired through document$ (not
// DOMContentLoaded) because navigation.instant swaps page content via
// history.pushState — a plain load listener would only ever fire once.
document$.subscribe(() => {
  // On an instant (SPA) navigation into this page, document$ can fire a
  // frame before the swapped-in content is actually attached to the live
  // DOM — the lookups below would miss and silently bail. Deferring to the
  // next frame lets that patch land first; a hard load already has the DOM
  // ready by the time this deferred/end-of-body script runs, so this is a
  // no-op there.
  requestAnimationFrame(() => {
    const select = document.getElementById("carrier-country-filter");
    const dataEl = document.getElementById("carriers-country-data");
    const table = document.querySelector("#carriers-block table");
    if (!select || !dataEl || !table) return;

    const countriesByRow = JSON.parse(dataEl.textContent);
    const rows = Array.from(table.querySelectorAll("tbody tr"));
    const countEl = document.getElementById("carrier-country-count");

    function apply() {
      const wanted = select.value;
      let shown = 0;
      rows.forEach((row, i) => {
        // No countries listed means cross-border/global — always relevant,
        // regardless of which country is selected.
        const countries = countriesByRow[i] || [];
        const visible = !wanted || countries.length === 0 || countries.includes(wanted);
        row.style.display = visible ? "" : "none";
        if (visible) shown += 1;
      });
      countEl.textContent = wanted ? `Showing ${shown} of ${rows.length} carriers` : "";
    }

    select.addEventListener("change", apply);
    apply();
  });
});
