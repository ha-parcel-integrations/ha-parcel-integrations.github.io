// The carrier grid on docs/carriers.md: filtering, and the detail dialog that
// replaced the old capability comparison page.
//
// Wired through document$ (not DOMContentLoaded) because navigation.instant
// swaps page content via history.pushState — a plain load listener would only
// ever fire once, and every SPA navigation back into this page would land on a
// dead grid.
document$.subscribe(() => {
  const dataEl = document.getElementById("carriers-data");
  const grid = document.getElementById("carriers-grid");
  const select = document.getElementById("carrier-country-filter");
  if (!dataEl || !grid || !select) return;

  const data = JSON.parse(dataEl.textContent);
  const bySlug = new Map(data.carriers.map((c) => [c.slug, c]));
  const countEl = document.getElementById("carrier-count");
  const emptyEl = document.getElementById("carriers-empty");
  const cards = Array.from(grid.querySelectorAll(".carrier-card"));
  const chips = Array.from(document.querySelectorAll(".carrier-chip"));
  const total = cards.length;

  // ---------------------------------------------------------------- filters

  const activeKinds = new Set();

  function apply() {
    const country = select.value;
    let shown = 0;

    cards.forEach((card) => {
      const countries = card.dataset.countries ? card.dataset.countries.split(" ") : [];
      const kinds = card.dataset.kinds.split(" ");
      // No countries listed means cross-border/global — always relevant,
      // regardless of which country is selected.
      const inCountry = !country || countries.length === 0 || countries.includes(country);
      const inKind = activeKinds.size === 0 || kinds.some((k) => activeKinds.has(k));
      const visible = inCountry && inKind;
      card.hidden = !visible;
      if (visible) shown += 1;
    });

    const filtered = Boolean(country) || activeKinds.size > 0;
    countEl.innerHTML = filtered
      ? `<strong>${shown} of ${total} carriers</strong>${
          country ? " — carriers without a country list deliver across borders and always match." : ""
        }`
      : `<strong>${total} carriers</strong> and counting.`;
    emptyEl.hidden = shown > 0;
  }

  select.addEventListener("change", apply);

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const kind = chip.dataset.kind;
      if (activeKinds.has(kind)) activeKinds.delete(kind);
      else activeKinds.add(kind);
      chip.setAttribute("aria-pressed", String(activeKinds.has(kind)));
      apply();
    });
  });

  // ----------------------------------------------------------------- dialog

  // Built once and reused: 60+ carriers means 60+ dialogs in the DOM
  // otherwise, and only one can ever be open.
  //
  // It lives inside .md-typeset, not on <body>: Material scopes its entire
  // typography — buttons, tables, headings — to that class, and a dialog
  // parented to <body> renders as unstyled browser defaults. showModal()
  // promotes it to the top layer either way, so nesting costs it nothing.
  const dialog = document.createElement("dialog");
  dialog.className = "carrier-dialog";
  dialog.tabIndex = -1;
  (document.querySelector(".md-content__inner") || document.body).appendChild(dialog);

  const escapes = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
  const esc = (value) => String(value).replace(/[&<>"]/g, (ch) => escapes[ch]);
  const flag = (code) =>
    String.fromCodePoint(...Array.from(code.toUpperCase(), (ch) => 127397 + ch.charCodeAt(0)));

  function coverage(carrier) {
    if (carrier.countries.length === 0) return "🌍 Worldwide";
    const flags = carrier.countries.map(flag).join(" ");
    return `<span class="carrier-flags">${flags}</span>`;
  }

  function connections(carrier) {
    return carrier.connections
      .map((conn) => {
        const pill = `<span class="carrier-pill carrier-pill--${conn.kind}">${esc(
          conn.label
        )}</span>`;
        // data/carriers.yml stores `input` mid-sentence ("tracking code");
        // it starts a line here, so it gets a capital.
        const detail = conn.input
          ? `<span class="carrier-input">${esc(
              conn.input.charAt(0).toUpperCase() + conn.input.slice(1)
            )}</span>`
          : "";
        const variant = conn.variant ? `<span class="carrier-variant">${esc(conn.variant)}</span>` : "";
        return `<li>${variant}${pill}${detail}</li>`;
      })
      .join("");
  }

  function capabilities(carrier) {
    if (!carrier.capabilities) {
      return (
        '<p class="carrier-note">This carrier has not declared its capabilities yet. ' +
        "Its own repo publishes them as it migrates — until then, expect the optional " +
        "fields to vary.</p>"
      );
    }
    const perBackend = carrier.capabilities.length > 1;
    const head = data.capabilityLabels
      .map(([, label, field]) => `<th scope="col"><abbr title="${esc(field)}">${esc(label)}</abbr></th>`)
      .join("");
    const rows = carrier.capabilities
      .map((entry) => {
        const cells = data.capabilityLabels
          .map(([key]) =>
            entry.fields.includes(key)
              ? '<td class="is-yes"><span aria-hidden="true">●</span><span class="sr-only">Populated</span></td>'
              : '<td class="is-no"><span aria-hidden="true">–</span><span class="sr-only">Always null</span></td>'
          )
          .join("");
        const label = perBackend ? `<th scope="row">${esc(entry.variant)}</th>` : "";
        return `<tr>${label}${cells}</tr>`;
      })
      .join("");
    const corner = perBackend ? '<th scope="col">Backend</th>' : "";
    const note = perBackend
      ? '<p class="carrier-note">This carrier runs a separate backend per country, so each one ' +
        "answers for itself — a field one country lacks is not missing everywhere.</p>"
      : "";
    return `<div class="carrier-table"><table class="carrier-caps"><thead><tr>${corner}${head}</tr></thead><tbody>${rows}</tbody></table></div>${note}`;
  }

  function render(carrier) {
    const beta = carrier.early ? '<span class="carrier-beta">Beta</span>' : "";
    const release = carrier.early
      ? "Early release — it works, but its status mapping was inferred rather than seen on a real parcel."
      : "Stable release.";
    // data/carriers.yml's `region` is the authored sentence — it names the
    // single country a flag alone leaves unlabelled, and explains the split
    // when a carrier runs a different backend per country.
    const region = `<span class="carrier-region">${esc(carrier.region)}</span>`;

    dialog.innerHTML = `
      <div class="carrier-dialog__head">
        <span class="carrier-plate">${
          carrier.icon
            ? `<img src="/assets/icons/${esc(carrier.icon)}" alt="">`
            : `<span class="carrier-initial">${esc(carrier.name.charAt(0))}</span>`
        }</span>
        <div class="carrier-dialog__title">
          <h2>${esc(carrier.name)} <span class="carrier-version">${esc(carrier.version)}</span> ${beta}</h2>
          <p>${esc(carrier.blurb)}</p>
          <a class="carrier-repo md-button md-button--primary" href="${esc(carrier.url)}"
             data-umami-event="carrier-click:${esc(carrier.repo)}">View on GitHub</a>
        </div>
        <button type="button" class="carrier-dialog__close" aria-label="Close">&times;</button>
      </div>
      <dl class="carrier-facts">
        <div>
          <dt>Connect with</dt>
          <dd><ul class="carrier-connections">${connections(carrier)}</ul></dd>
        </div>
        <div>
          <dt>Tracks</dt>
          <dd>${carrier.directions === "incoming+outgoing" ? "Incoming &amp; outgoing" : "Incoming"}</dd>
        </div>
        <div>
          <dt>Delivers in</dt>
          <dd>${coverage(carrier)}${region}</dd>
        </div>
      </dl>
      <section class="carrier-capabilities">
        <h3>Capabilities</h3>
        <p class="carrier-note">Which optional
          <a href="../contract/#the-parcel-shape">parcel fields</a> this carrier actually
          populates. A dash means its API never exposes that field — nothing to configure.</p>
        ${capabilities(carrier)}
      </section>
      <p class="carrier-dialog__foot">${esc(release)}</p>
    `;
    dialog.querySelector(".carrier-dialog__close").addEventListener("click", () => dialog.close());
  }

  function open(slug) {
    const carrier = bySlug.get(slug);
    if (!carrier) return;
    render(carrier);
    dialog.showModal();
    // showModal() otherwise autofocuses the first focusable child, which is
    // the GitHub button — it opens looking pressed, and a screen reader
    // starts halfway down. Focusing the dialog starts at the carrier's name.
    dialog.focus();
    if (history.replaceState) history.replaceState(null, "", `#${slug}`);
  }

  grid.addEventListener("click", (event) => {
    const card = event.target.closest(".carrier-card");
    if (card) open(card.dataset.slug);
  });

  // A click on the dialog element itself (not on its contents) is a click on
  // the backdrop, which should dismiss it the way Escape does.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  // Drop the fragment again so a reload, or a copied URL after browsing
  // around, does not reopen a carrier the reader already closed.
  dialog.addEventListener("close", () => {
    if (location.hash && history.replaceState) {
      history.replaceState(null, "", location.pathname + location.search);
    }
  });

  // /carriers/#gls opens GLS straight away — that is what the links that used
  // to point at the capability comparison resolve to now.
  if (location.hash) open(decodeURIComponent(location.hash.slice(1)));

  apply();
});
