// CDISC Standards Browser - a standalone window opened from the main editor's sidebar,
// deliberately independent of app.js: it has nothing to do with editing the define/ file
// tree, only with looking up Controlled Terminology and standards metadata.
//
// Two sources, both local-first:
//   1. NCI EVS Controlled Terminology (defineyaml/cdisc/nci_evs.py) - published CDISC CT,
//      one file per (standard, version), downloaded once and cached on disk.
//   2. A user-configured folder of CDISC CSV exports (defineyaml/cdisc/local_standards.py).
//
// The CDISC Library API integration is retired - its client/config/cache modules are
// still in the tree but nothing routes to them, and this page no longer surfaces them.

function el(tag, props, children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) e.setAttribute(k, v);
  }
  for (const c of [].concat(children || [])) {
    if (c === null || c === undefined) continue;
    e.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }
  return e;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

async function apiGet(url) {
  const r = await fetch(url);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`);
  return body;
}

async function apiSend(method, url, data) {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`);
  return body;
}

const API = {
  nciEvsStandards: () => apiGet("/api/cdisc/nci-evs/standards"),
  nciEvsVersions: (standard, force) => apiGet(`/api/cdisc/nci-evs/${standard}/versions?force=${force ? "true" : "false"}`),
  nciEvsDownload: (standard, version, force) =>
    apiSend("POST", `/api/cdisc/nci-evs/${standard}/download?version=${encodeURIComponent(version)}&force=${force ? "true" : "false"}`),
  nciEvsCodelists: (standard, version) =>
    apiGet(`/api/cdisc/nci-evs/${standard}/codelists?version=${encodeURIComponent(version)}`),
  nciEvsCodelistTerms: (standard, version, oid) =>
    apiGet(`/api/cdisc/nci-evs/${standard}/codelists/${encodeURIComponent(oid)}?version=${encodeURIComponent(version)}`),
  nciEvsSaveToFolder: (standard, version) =>
    apiSend("POST", `/api/cdisc/nci-evs/${standard}/save-to-folder?version=${encodeURIComponent(version)}`),
  standardsConfig: () => apiGet("/api/standards/config"),
  setStandardsConfig: (folder) => apiSend("PUT", "/api/standards/config", { folder }),
  createStandardsFolder: () => apiSend("POST", "/api/standards/config/create-folder"),
  standardsFiles: () => apiGet("/api/standards/files"),
  standardsFile: (path, q, limit, offset) =>
    apiGet(`/api/standards/file?path=${encodeURIComponent(path)}&q=${encodeURIComponent(q || "")}&limit=${limit}&offset=${offset}`),
  standardsSearch: (q, limit) => apiGet(`/api/standards/search?q=${encodeURIComponent(q)}&limit=${limit || 200}`),
};

function formatBytes(n) {
  if (!n && n !== 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatWhen(epochSeconds) {
  if (!epochSeconds) return "";
  return new Date(epochSeconds * 1000).toLocaleString();
}

function versionLabel(v) {
  return v; // NCI EVS releases are all dated now - no "current" pseudo-version
}

// --- NCI EVS -----------------------------------------------------------------------

let nciEvsDownloaded = {}; // standard -> [version, ...]

async function renderNciEvsStandards() {
  const box = document.getElementById("cdisc-nci-evs-standards");
  clear(box);
  let standards;
  try {
    standards = await API.nciEvsStandards();
  } catch (err) {
    box.appendChild(el("div", { class: "cdisc-error" }, `Could not check NCI EVS cache: ${err.message || err}`));
    return;
  }
  nciEvsDownloaded = {};
  for (const entry of standards) {
    nciEvsDownloaded[entry.standard] = entry.downloaded || [];
    box.appendChild(renderNciEvsCard(entry.standard, entry.downloaded || []));
  }
}

function renderNciEvsCard(standard, downloaded) {
  const card = el("div", { class: "cdisc-nci-evs-card" });
  card.appendChild(el("div", { class: "cdisc-nci-evs-card-name" }, standard));
  card.appendChild(
    el(
      "div",
      { class: "cdisc-nci-evs-card-status" },
      downloaded.length
        ? `On disk: ${downloaded.map(versionLabel).join(", ")}`
        : "Nothing downloaded yet"
    )
  );

  const versionArea = el("div", { class: "cdisc-nci-evs-version-area" });
  const actions = el("div", { class: "cdisc-panel-actions" });

  async function showVersionPicker(force) {
    clear(versionArea);
    versionArea.appendChild(el("div", { class: "cdisc-loading" }, force ? "Checking NCI EVS for new releases…" : "Listing available versions…"));
    let versions;
    try {
      versions = await API.nciEvsVersions(standard, force);
    } catch (err) {
      clear(versionArea);
      versionArea.appendChild(el("div", { class: "cdisc-error" }, `Could not list versions: ${err.message || err}`));
      return;
    }
    clear(versionArea);
    const select = el("select", { class: "cdisc-nci-evs-version-select" });
    for (const v of versions) {
      const parts = [versionLabel(v.version)];
      if (v.size) parts.push(formatBytes(v.size));
      if (v.downloaded) parts.push("✓ downloaded");
      select.appendChild(el("option", { value: v.version }, parts.join(" - ")));
    }
    const browseBtn = el(
      "button",
      {
        class: "primary",
        type: "button",
        onclick: () => browseNciEvsVersion(standard, select.value),
      },
      "Download & browse"
    );
    const refreshBtn = el(
      "button",
      { class: "secondary", type: "button", title: "Re-query NCI EVS for newer releases", onclick: () => showVersionPicker(true) },
      "Check for updates"
    );
    versionArea.appendChild(el("div", { class: "cdisc-nci-evs-version-row" }, [select, browseBtn, refreshBtn]));
  }

  actions.appendChild(el("button", { class: "secondary", type: "button", onclick: () => showVersionPicker(false) }, "List versions"));
  for (const v of downloaded) {
    actions.appendChild(
      el("button", { class: "secondary", type: "button", onclick: () => browseNciEvsVersion(standard, v) }, `Browse ${versionLabel(v).toLowerCase()}`)
    );
  }

  card.appendChild(actions);
  card.appendChild(versionArea);
  return card;
}

async function browseNciEvsVersion(standard, version) {
  const browser = document.getElementById("cdisc-nci-evs-browser");
  clear(browser);
  const alreadyLocal = (nciEvsDownloaded[standard] || []).includes(version);
  browser.appendChild(
    el(
      "div",
      { class: "cdisc-loading" },
      alreadyLocal
        ? `Loading ${standard} ${versionLabel(version)}…`
        : `Downloading ${standard} ${versionLabel(version)} (first time only - this is a real 0.1–25 MB file)…`
    )
  );
  let codelists;
  try {
    if (!alreadyLocal) await API.nciEvsDownload(standard, version, false);
    codelists = await API.nciEvsCodelists(standard, version);
  } catch (err) {
    clear(browser);
    browser.appendChild(el("div", { class: "cdisc-error" }, `Could not load ${standard} ${versionLabel(version)}: ${err.message || err}`));
    return;
  }
  renderNciEvsCodelistBrowser(standard, version, codelists);
  await renderNciEvsStandards();
}

function renderNciEvsCodelistBrowser(standard, version, codelists) {
  const browser = document.getElementById("cdisc-nci-evs-browser");
  clear(browser);
  const caption = el("div", { class: "cdisc-self-caption" }, [el("span", {}, `${standard} - ${version}`)]);
  browser.appendChild(caption);
  addSaveToFolderButton(caption, standard, version);
  const searchInput = el("input", {
    type: "text",
    class: "cdisc-nci-evs-search",
    placeholder: `Search ${codelists.length} codelists by name or NCI code…`,
  });
  const countLabel = el("div", { class: "cdisc-query-meta" }, `${codelists.length} codelists`);
  const list = el("div", { class: "cdisc-nci-evs-codelist-list" });
  const termsBox = el("div", { class: "cdisc-nci-evs-terms" });

  function renderList(filterText) {
    clear(list);
    const needle = (filterText || "").trim().toLowerCase();
    const matches = needle
      ? codelists.filter((c) => (c.name || "").toLowerCase().includes(needle) || (c.nci_code || "").toLowerCase().includes(needle))
      : codelists;
    countLabel.textContent = needle ? `${matches.length} of ${codelists.length} codelists` : `${codelists.length} codelists`;
    for (const cl of matches.slice(0, 300)) {
      list.appendChild(
        el(
          "button",
          { class: "cdisc-nci-evs-codelist-item", type: "button", onclick: () => loadNciEvsTerms(standard, version, cl, termsBox) },
          [
            cl.name || cl.oid,
            cl.nci_code ? el("span", { class: "cdisc-link-type" }, cl.nci_code) : null,
            cl.extensible ? el("span", { class: "cdisc-access-badge cdisc-access-hint" }, "extensible") : null,
          ]
        )
      );
    }
    if (matches.length > 300) {
      list.appendChild(el("div", { class: "cdisc-query-meta" }, `…and ${matches.length - 300} more - keep typing to narrow it down.`));
    }
  }

  searchInput.addEventListener("input", () => renderList(searchInput.value));
  renderList("");
  browser.appendChild(searchInput);
  browser.appendChild(countLabel);
  browser.appendChild(el("div", { class: "cdisc-nci-evs-layout" }, [list, termsBox]));
}

// When a local Standards folder is configured, offer to save this whole CT release
// into it as a CDISC-DSB-style CSV (terminology/<standard>/<STD>_CT_<date>.csv) - it
// then scaffolds datasets/codelists like any hand-downloaded export.
async function addSaveToFolderButton(host, standard, version) {
  let cfg;
  try {
    cfg = await API.standardsConfig();
  } catch {
    return;
  }
  if (!cfg || !cfg.exists) return;

  const msg = el("span", { class: "cdisc-save-msg" }, "");
  const btn = el(
    "button",
    {
      class: "secondary",
      type: "button",
      title: `Write terminology/${standard.toLowerCase()}/${standard}_CT_${version}.csv into ${cfg.resolved}`,
      onclick: async () => {
        btn.disabled = true;
        msg.textContent = "Saving…";
        try {
          const r = await API.nciEvsSaveToFolder(standard, version);
          msg.textContent = `${r.existed ? "Overwrote" : "Saved"} ${r.path} (${formatBytes(r.bytes)})`;
          if (typeof renderStandardsFiles === "function") await renderStandardsFiles();
        } catch (err) {
          msg.textContent = `Error: ${err.message || err}`;
        } finally {
          btn.disabled = false;
        }
      },
    },
    "Save to standards folder",
  );
  host.appendChild(btn);
  host.appendChild(msg);
}

async function loadNciEvsTerms(standard, version, codelistMeta, termsBox) {
  clear(termsBox);
  termsBox.appendChild(el("div", { class: "cdisc-loading" }, "Loading terms…"));
  try {
    const result = await API.nciEvsCodelistTerms(standard, version, codelistMeta.oid);
    clear(termsBox);
    termsBox.appendChild(
      el("div", { class: "cdisc-self-caption" }, `${result.name} - ${result.terms.length} terms${result.extensible ? " (extensible)" : ""}`)
    );
    const table = el("table", { class: "cdisc-nci-evs-terms-table" }, [
      el("thead", {}, [el("tr", {}, [el("th", {}, "Code"), el("th", {}, "Preferred Term"), el("th", {}, "NCI Code"), el("th", {}, "Definition")])]),
      el(
        "tbody",
        {},
        result.terms.map((t) =>
          el("tr", {}, [
            el("td", { class: "cdisc-json-scalar" }, t.code || ""),
            el("td", {}, t.decode || t.preferred_term || t.synonym || ""),
            el("td", { class: "cdisc-json-scalar" }, t.nci_code || ""),
            el("td", { class: "cdisc-nci-evs-definition" }, t.definition || ""),
          ])
        )
      ),
    ]);
    termsBox.appendChild(table);
  } catch (err) {
    clear(termsBox);
    termsBox.appendChild(el("div", { class: "cdisc-error" }, `Could not load terms for ${codelistMeta.name}: ${err.message || err}`));
  }
}

// --- Local standards folder -------------------------------------------------------

let standardsFolder = null;

async function renderStandardsConfig() {
  const box = document.getElementById("cdisc-standards-config");
  clear(box);
  let config;
  try {
    config = await API.standardsConfig();
  } catch (err) {
    box.appendChild(el("div", { class: "cdisc-error" }, `Could not read config: ${err.message || err}`));
    return;
  }
  // Per-tree now (stored in this tree's standards.yaml, not a global setting). `folder`
  // is the raw stored value; `resolved`/`exists` say whether it currently points at a
  // real directory. Downstream panels only work when it resolves.
  const rawFolder = config.folder || null;
  standardsFolder = config.exists ? config.resolved : null;

  const input = el("input", { type: "text", placeholder: "/path/to/standards/csv/folder", value: rawFolder || "" });
  const msg = el("span", { class: "cdisc-save-msg" }, rawFolder && !config.exists ? `⚠ ${config.error || "does not resolve"}` : "");
  const saveBtn = el(
    "button",
    {
      class: "primary",
      type: "button",
      onclick: async () => {
        msg.textContent = "Saving…";
        try {
          await API.setStandardsConfig(input.value.trim());
          msg.textContent = "Saved.";
          await renderStandardsConfig();
          await renderStandardsFiles();
          await renderStandardsSearch();
        } catch (err) {
          msg.textContent = `Error: ${err.message || err}`;
        }
      },
    },
    rawFolder ? "Change folder" : "Set folder"
  );

  // The path is set but nothing's there yet (a folder not made, or a cloned/moved tree).
  const createBtn = config.creatable
    ? el(
        "button",
        {
          class: "secondary",
          type: "button",
          onclick: async () => {
            msg.textContent = "Creating…";
            try {
              await API.createStandardsFolder();
              msg.textContent = "Created.";
              await renderStandardsConfig();
              await renderStandardsFiles();
              await renderStandardsSearch();
            } catch (err) {
              msg.textContent = `Error: ${err.message || err}`;
            }
          },
        },
        "Create this folder",
      )
    : null;

  if (standardsFolder) {
    box.appendChild(el("div", { class: "cdisc-query-meta" }, [el("span", { class: "cdisc-json-scalar" }, standardsFolder)]));
  }
  box.appendChild(el("div", { class: "cdisc-field-row" }, [el("label", {}, "Folder"), input, el("div", { class: "cdisc-field-hint" }, "Stored in this tree's standards.yaml. Absolute, or relative to the define/ tree.")]));
  box.appendChild(el("div", { class: "cdisc-actions" }, [saveBtn, createBtn, msg].filter(Boolean)));
}

async function renderStandardsSearch() {
  const box = document.getElementById("cdisc-standards-search");
  clear(box);
  if (!standardsFolder) return;
  const input = el("input", { type: "text", class: "cdisc-nci-evs-search", placeholder: "Search every CSV in the folder (variable name, codelist, term, …)" });
  const results = el("div", { id: "cdisc-standards-search-results" });

  async function run() {
    const q = input.value.trim();
    clear(results);
    if (!q) return;
    results.appendChild(el("div", { class: "cdisc-loading" }, "Searching…"));
    let data;
    try {
      data = await API.standardsSearch(q, 200);
    } catch (err) {
      clear(results);
      results.appendChild(el("div", { class: "cdisc-error" }, `${err.message || err}`));
      return;
    }
    clear(results);
    results.appendChild(
      el("div", { class: "cdisc-query-meta" }, `${data.matches.length}${data.truncated ? "+" : ""} matches across ${data.files_scanned} files`)
    );
    const byFile = {};
    for (const m of data.matches) (byFile[m.file] = byFile[m.file] || []).push(m.row);
    for (const [file, rows] of Object.entries(byFile)) {
      const group = el("div", { class: "cdisc-relation" });
      group.appendChild(
        el("div", { class: "cdisc-relation-header" }, [
          el("span", { class: "cdisc-relation-label", onclick: () => openStandardsFile(file, q) }, [
            file,
            el("span", { class: "cdisc-relation-count" }, `(${rows.length})`),
          ]),
        ])
      );
      group.appendChild(compactRowsTable(rows.slice(0, 8)));
      results.appendChild(group);
    }
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") run();
  });
  box.appendChild(el("div", { class: "cdisc-field-row" }, [el("label", {}, "Global search"), input, el("div", { class: "cdisc-field-hint" }, "Press Enter to search. Click a file heading to open it filtered.")]));
  box.appendChild(results);
}

function compactRowsTable(rows) {
  if (!rows.length) return el("div", {}, []);
  const cols = Object.keys(rows[0]);
  return el("div", { class: "cdisc-table-scroll" }, [
    el("table", { class: "cdisc-nci-evs-terms-table" }, [
      el("thead", {}, [el("tr", {}, cols.map((c) => el("th", {}, c)))]),
      el("tbody", {}, rows.map((r) => el("tr", {}, cols.map((c) => el("td", {}, r[c] || ""))))),
    ]),
  ]);
}

async function renderStandardsFiles() {
  const box = document.getElementById("cdisc-standards-body");
  clear(box);
  if (!standardsFolder) {
    box.appendChild(el("div", { class: "cdisc-query-meta" }, "Set a folder above to browse its CSV files."));
    return;
  }
  let data;
  try {
    data = await API.standardsFiles();
  } catch (err) {
    box.appendChild(el("div", { class: "cdisc-error" }, `${err.message || err}`));
    return;
  }
  const layout = el("div", { class: "cdisc-standards-layout" });
  const nav = el("div", { class: "cdisc-standards-nav" });
  const view = el("div", { class: "cdisc-standards-view", id: "cdisc-standards-file-view" });

  let total = 0;
  for (const group of data.categories) {
    total += group.files.length;
    const items = el("div", { class: "cdisc-relation-items" });
    for (const f of group.files) {
      items.appendChild(
        el("button", { class: "cdisc-nci-evs-codelist-item", type: "button", title: f.path, onclick: () => openStandardsFile(f.path, "") }, [
          f.name,
          f.version ? el("span", { class: "cdisc-link-type" }, f.version) : null,
          f.size ? el("span", { class: "cdisc-link-type" }, formatBytes(f.size)) : null,
        ])
      );
    }
    nav.appendChild(el("div", { class: "cdisc-self-caption" }, group.category || "(root)"));
    nav.appendChild(items);
  }
  view.appendChild(el("div", { class: "cdisc-query-meta" }, `${total} CSV files - pick one to view.`));
  layout.appendChild(nav);
  layout.appendChild(view);
  box.appendChild(layout);
}

const FILE_PAGE = 500;

async function openStandardsFile(path, q) {
  const view = document.getElementById("cdisc-standards-file-view");
  if (!view) return;
  clear(view);
  view.appendChild(el("div", { class: "cdisc-self-caption" }, path));

  const search = el("input", { type: "text", class: "cdisc-nci-evs-search", value: q || "", placeholder: "Filter rows (all columns)…" });
  const raw = el("a", { class: "cdisc-link-type", href: `/api/standards/raw?path=${encodeURIComponent(path)}`, target: "_blank" }, "download raw CSV");
  const meta = el("div", { class: "cdisc-query-meta" }, "");
  const tableBox = el("div", {});
  const moreBox = el("div", {});
  view.appendChild(el("div", { class: "cdisc-standards-file-toolbar" }, [search, raw]));
  view.appendChild(meta);
  view.appendChild(tableBox);
  view.appendChild(moreBox);

  let offset = 0;
  let loaded = [];
  let columns = [];

  async function load(reset) {
    if (reset) {
      offset = 0;
      loaded = [];
    }
    let data;
    try {
      data = await API.standardsFile(path, search.value.trim(), FILE_PAGE, offset);
    } catch (err) {
      clear(tableBox);
      tableBox.appendChild(el("div", { class: "cdisc-error" }, `${err.message || err}`));
      return;
    }
    columns = data.columns;
    loaded = loaded.concat(data.rows);
    offset += data.rows.length;
    meta.textContent = `${loaded.length} of ${data.total_matched} row(s)${search.value.trim() ? ` matching "${search.value.trim()}"` : ""}`;
    clear(tableBox);
    tableBox.appendChild(compactRowsTable(loaded));
    clear(moreBox);
    if (data.truncated) {
      moreBox.appendChild(el("button", { class: "secondary", type: "button", onclick: () => load(false) }, `Load ${FILE_PAGE} more`));
    }
  }

  let debounce;
  search.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => load(true), 250);
  });
  load(true);
}

async function boot() {
  await Promise.all([renderNciEvsStandards(), renderStandardsConfig()]);
  await renderStandardsSearch();
  await renderStandardsFiles();
}

boot();
