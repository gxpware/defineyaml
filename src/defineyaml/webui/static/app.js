// define edit - a small, dependency-free (no build step) editor UI over the
// /api/kinds/{kind}/items/{key} REST API in server.py.
//
// Editing model: loading an object clones the FULL loaded JSON into
// `state.working`. Every widget mutates a specific key of that object in
// place (`working.name = ...`, `working.variables[i].label = ...`) rather
// than rebuilding the payload from only the fields a widget exists for -
// that's what lets a field this UI has no dedicated control for (e.g. a rare
// nested attribute) still round-trip untouched: it was never removed from
// `working` in the first place. On Save the *whole* working object is PUT
// back; the server (tree.py's _merge) folds it into the on-disk YAML,
// preserving comments on whatever key or list item didn't change shape.
//
// Every editor also has a raw-JSON fallback (see rawToggle()) for whatever
// this session's structured widgets don't cover - full editability without
// full hand-built coverage of every nested model.

// Kinds addressed by a fixed file (study.yaml/standards.yaml/documents.yaml) rather
// than one file per item - no "new"/"delete", and "used by/orphan" isn't a meaningful
// question at that granularity (see usages.py's own note on this).
const SINGLETON_KINDS = { study: true, standards: true, documents: true };

const state = {
  kinds: [],
  itemsByKind: {},
  selection: null, // {kind, key}
  working: null,
  usages: null, // {used_by: [{kind,key,label,field}], orphan} for the current selection
  raw: false,
  autosave: false,
  dirty: false,
};

// Set by renderEditor() to its doSave() closure, so field widgets (which don't have
// access to that closure) can trigger a save via notifyDirty() when autosave is on.
let currentSave = null;
let autosaveTimer = null;
const AUTOSAVE_DEBOUNCE_MS = 900;

function notifyDirty() {
  state.dirty = true;
  updateDirtyIndicator();
  if (!state.autosave || !currentSave) return;
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => currentSave(), AUTOSAVE_DEBOUNCE_MS);
}

function updateDirtyIndicator() {
  const el = document.getElementById("dirty-indicator");
  if (el) el.textContent = state.dirty ? (state.autosave ? "saving…" : "unsaved changes") : "";
}

// Closing/reloading the tab with an unsaved edit would silently discard it - same risk
// notifyDirty()'s autosave path exists to avoid, but autosave can be off, or a save may
// still be sitting in its debounce window. state.dirty is already false the instant a
// save actually lands (doSave(), the autosave path, and resetEditingState() all clear
// it), so this only fires when there's something genuinely unsaved. No custom message:
// every modern browser shows its own generic text regardless of returnValue's content -
// setting it (old-style) alongside preventDefault() (current standard) is what actually
// triggers the native confirm dialog across browsers.
window.addEventListener("beforeunload", (e) => {
  if (!state.dirty) return;
  e.preventDefault();
  e.returnValue = "";
});

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

function encodeKey(key) {
  return key.split("/").map(encodeURIComponent).join("/");
}

// A thin indeterminate bar at the top of the window shows while any request is in
// flight - every call routes through apiGet/apiSend, so this covers boot, object
// switches, saves and the scaffold/standards calls without each wiring its own spinner.
let pendingRequests = 0;
function requestStarted() {
  pendingRequests += 1;
  const bar = document.getElementById("load-bar");
  if (bar) bar.classList.add("active");
}
function requestFinished() {
  pendingRequests = Math.max(0, pendingRequests - 1);
  if (pendingRequests === 0) {
    const bar = document.getElementById("load-bar");
    if (bar) bar.classList.remove("active");
  }
}

async function apiGet(url) {
  requestStarted();
  try {
    const r = await fetch(url);
    const body = await r.json();
    if (!r.ok) throw { status: r.status, body };
    return body;
  } finally {
    requestFinished();
  }
}

async function apiSend(method, url, data) {
  requestStarted();
  try {
    const r = await fetch(url, {
      method,
      headers: data !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: data !== undefined ? JSON.stringify(data) : undefined,
    });
    const body = await r.json();
    if (!r.ok) throw { status: r.status, body };
    return body;
  } finally {
    requestFinished();
  }
}

// A centered spinner + label, for a pane whose content is still being fetched.
function loadingBlock(text) {
  return el("div", { class: "loading-block" }, [el("span", { class: "spinner" }), text || "Loading…"]);
}

const API = {
  info: () => apiGet("/api/info"),
  kinds: () => apiGet("/api/kinds"),
  items: (kind) => apiGet(`/api/kinds/${kind}/items`),
  get: (kind, key) => apiGet(`/api/kinds/${kind}/items/${encodeKey(key)}`),
  save: (kind, key, data) => apiSend("PUT", `/api/kinds/${kind}/items/${encodeKey(key)}`, data),
  remove: (kind, key) => apiSend("DELETE", `/api/kinds/${kind}/items/${encodeKey(key)}`),
  getEditorState: () => apiGet("/api/state"),
  putEditorState: (data) => apiSend("PUT", "/api/state", data),
  putDatasetOrder: (order) => apiSend("PUT", "/api/datasets/order", { order }),
  setupStatus: () => apiGet("/api/setup/status"),
  setupRecent: () => apiGet("/api/setup/recent"),
  setupBrowse: (path) => apiGet(`/api/setup/browse${path ? `?path=${encodeURIComponent(path)}` : ""}`),
  setupOpen: (path) => apiSend("POST", "/api/setup/open", { path }),
  setupInit: (body) => apiSend("POST", "/api/setup/init", body),
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

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

function get(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
}

function set(obj, path, value) {
  const parts = path.split(".");
  const last = parts.pop();
  let node = obj;
  for (const p of parts) {
    if (node[p] == null) node[p] = {};
    node = node[p];
  }
  node[last] = value;
}

// ---------------------------------------------------------------------------
// Field widgets - each takes (label, value, onChange, opts) and returns a .field-row
// ---------------------------------------------------------------------------

function fieldRow(label, control, hint) {
  return el("div", { class: "field-row" }, [el("label", {}, label), control, hint ? el("div", { class: "field-hint" }, hint) : null]);
}

// Live validation on a field row (or a table cell wrapper): `validate(value)` returns
// null when fine, a string for an error, or {msg, warn:true} for a softer amber flag.
// Re-runs on every input/change bubbling out of the row, reading the control's own value
// (so it doesn't need the item/key). Purely a visual aid - the server's pydantic pass is
// still what actually blocks a bad save.
function attachValidation(row, validate) {
  if (typeof validate !== "function") return row;
  const msg = el("div", { class: "field-error" });
  row.appendChild(msg);
  const run = () => {
    const input = row.querySelector("input, select, textarea");
    const value = !input ? "" : input.type === "checkbox" ? input.checked : input.value;
    const r = validate(value);
    const warn = !!r && typeof r === "object" && r.warn;
    row.classList.toggle("has-error", !!r && !warn);
    row.classList.toggle("has-warn", warn);
    msg.textContent = r ? r.msg || r : "";
  };
  row.addEventListener("input", run);
  row.addEventListener("change", run);
  run();
  return row;
}

// A few reusable validators for the field specs / *Field opts.
function requiredField(label) {
  return (v) => (v == null || String(v).trim() === "" ? `${label} is required` : null);
}
function maxLenField(label, max) {
  return (v) => (v && String(v).length > max ? { warn: true, msg: `${String(v).length} chars - over the ${max}-char limit` } : null);
}

// A CDISC / SAS-v5-transport variable name is uppercase, ≤8 chars, starts with a letter or
// underscore, and is letters/digits/underscore throughout - and a `--`-prefixed or
// lowercase-templated name (SMQzzSC, --SEQ) is a placeholder that should have been
// instantiated. None of this is rejected on save (the model takes any `str`); this just
// returns an amber {warn} so the field flags it. Returns null for a blank value -
// required-ness is a separate (hard) check.
function variableNameWarnings(v) {
  const name = (v == null ? "" : String(v)).trim();
  if (!name) return null;
  // A `--`/`xx`-style placeholder: report only that - the "bad start char" / "bad chars"
  // rules below would just be noise on a name that's meant to be replaced wholesale.
  if (name.startsWith("--")) {
    return { warn: true, msg: "starts with “--”: replace the domain-prefix placeholder with the real domain" };
  }
  const issues = [];
  if (name.length > 8) issues.push(`${name.length} chars - over the 8-char SAS v5 transport limit`);
  if (/[a-z]/.test(name)) issues.push("has lowercase letters - CDISC names are uppercase; a templated name must be instantiated");
  if (!/^[A-Za-z_]/.test(name)) issues.push("must start with a letter or underscore");
  if (/[^A-Za-z0-9_]/.test(name)) issues.push("has characters other than letters, digits and underscore");
  return issues.length ? { warn: true, msg: issues.join("; ") } : null;
}

// Every field widget's onChange goes through this so an edit anywhere marks the
// object dirty and (if autosave is on) schedules a save - one place, rather than
// wiring notifyDirty() into each widget's own event listener individually.
function notified(onChange) {
  return (v) => {
    onChange(v);
    notifyDirty();
  };
}

// Each *Control builds the bare input/select/textarea element with its onChange wiring
// (notified, so notifyDirty()/autosave still fire) and nothing else - no label, no
// field-row wrapper. The matching *Field wraps one in fieldRow() for the vertical
// structured-form layout; buildCellFromSpec (below) uses the same controls bare, for a
// table layout where the column header already says what the field is.
function textControl(value, onChange, opts = {}) {
  onChange = notified(onChange);
  const input = el("input", { type: "text", oninput: (e) => onChange(e.target.value || null), placeholder: opts.placeholder || "" });
  input.value = value ?? "";
  if (opts.disabled) input.disabled = true;
  // opts.onCommit fires on `change` (blur / datalist pick), not every keystroke - for
  // fields that populate siblings and want a re-render once the value settles.
  if (opts.onCommit) input.addEventListener("change", () => opts.onCommit(input.value || null));
  return withDatalist(input, opts.suggestions);
}
function textField(label, value, onChange, opts = {}) {
  return attachValidation(fieldRow(label, textControl(value, onChange, opts), opts.hint), opts.validate);
}

function numberControl(value, onChange, opts = {}) {
  onChange = notified(onChange);
  const input = el("input", { type: "number", placeholder: opts.placeholder || "", oninput: (e) => onChange(e.target.value === "" ? null : Number(e.target.value)) });
  input.value = value ?? "";
  return input;
}
function numberField(label, value, onChange, opts = {}) {
  return attachValidation(fieldRow(label, numberControl(value, onChange), opts.hint), opts.validate);
}

function checkboxControl(value, onChange) {
  onChange = notified(onChange);
  const input = el("input", { type: "checkbox", onchange: (e) => onChange(e.target.checked) });
  input.checked = !!value;
  return input;
}
function checkboxField(label, value, onChange) {
  const wrap = el("label", { style: "display:flex;align-items:center;gap:6px;font-weight:600;font-size:12px;color:var(--text-dim);" }, [checkboxControl(value, onChange), label]);
  return el("div", { class: "field-row" }, [wrap]);
}

function textareaControl(value, onChange, opts = {}) {
  onChange = notified(onChange);
  const ta = el("textarea", { class: opts.code ? "code" : "", placeholder: opts.placeholder || "", oninput: (e) => onChange(e.target.value || null) });
  ta.value = value ?? "";
  return ta;
}
function textareaField(label, value, onChange, opts = {}) {
  return attachValidation(fieldRow(label, textareaControl(value, onChange, opts), opts.hint), opts.validate);
}

function selectControl(value, options, onChange, opts = {}) {
  onChange = notified(onChange);
  const select = el("select", { onchange: (e) => { onChange(e.target.value || null); select.classList.toggle("is-empty", !e.target.value); } });
  if (!opts.required) select.appendChild(el("option", { value: "" }, opts.placeholder || "-"));
  for (const opt of options) {
    const o = el("option", { value: opt }, opt);
    if (opt === value) o.selected = true;
    select.appendChild(o);
  }
  if (!value) select.classList.add("is-empty");
  return select;
}
function selectField(label, value, options, onChange, opts = {}) {
  return attachValidation(fieldRow(label, selectControl(value, options, onChange, opts), opts.hint), opts.validate);
}

function refToText(ref) {
  if (ref == null) return "";
  if (typeof ref === "string") return ref;
  if (typeof ref === "object" && ref.oid) return `oid:${ref.oid}`;
  return "";
}
function textToRef(text) {
  if (!text) return null;
  if (text.startsWith("oid:")) return { oid: text.slice(4).trim() };
  return text;
}
function refControl(value, onChange, opts = {}) {
  onChange = notified(onChange);
  const input = el("input", { type: "text", class: "ref-input", placeholder: opts.placeholder || "name, or oid:LITERAL", oninput: (e) => onChange(textToRef(e.target.value)) });
  input.value = refToText(value);
  // opts.onPicker(currentText, setValue): a double-click opens a search/create picker;
  // setValue(name) writes the choice back through the same `input` event path a keystroke
  // would, so attachValidation and notifyDirty()/autosave still fire.
  if (opts.onPicker) {
    input.title = "Double-click to search or create";
    input.addEventListener("dblclick", () =>
      opts.onPicker(input.value || "", (picked) => {
        input.value = picked || "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      })
    );
  }
  return withDatalist(input, opts.suggestions);
}
function refField(label, value, onChange, optsOrHint) {
  const opts = typeof optsOrHint === "string" || optsOrHint == null ? { hint: optsOrHint } : optsOrHint;
  return attachValidation(fieldRow(label, refControl(value, onChange, opts), opts.hint || "Reference by name, or oid:LITERAL for a literal OID override."), opts.validate);
}

// Wraps an <input> with a sibling <datalist> of suggestions (returns a fragment), or the
// bare input when there are none. Shared by textControl and refControl.
function withDatalist(input, suggestions) {
  if (!suggestions || !suggestions.length) return input;
  const listId = "dl-" + Math.random().toString(36).slice(2, 9);
  input.setAttribute("list", listId);
  const frag = document.createDocumentFragment();
  frag.appendChild(input);
  frag.appendChild(el("datalist", { id: listId }, suggestions.slice(0, 500).map((s) => el("option", { value: s }))));
  return frag;
}

function stringListControl(value, onChange, opts = {}) {
  onChange = notified(onChange);
  const input = el("input", { type: "text", placeholder: opts.placeholder || "", oninput: (e) => onChange(e.target.value ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean) : []) });
  input.value = (value || []).join(", ");
  return input;
}
function stringListField(label, value, onChange, hint) {
  return fieldRow(label, stringListControl(value, onChange), hint || "Comma-separated.");
}

// def:PDFPageRef page references. The value is a union (matching the model's `Pages`):
//   [4, 5]            list of integers  -> Type="PhysicalRef", PageRefs
//   ["section2.1"]    list of strings   -> Type="NamedDestination", PageRefs
//   {first, last}     a page range      -> FirstPage/LastPage
// which the emitter infers Type back out from - so the editor just needs to round-trip
// the shape. A text field is the natural input: "4 5", "112-114", "section2.1".
function pagesToText(p) {
  if (p == null) return "";
  if (Array.isArray(p)) return p.join(" ");
  if (typeof p === "object" && p.first != null) return `${p.first}-${p.last}`;
  return "";
}
function textToPages(s) {
  s = (s || "").trim();
  if (!s) return null;
  const range = s.match(/^(\d+)\s*[-–]\s*(\d+)$/);
  if (range) return { first: Number(range[1]), last: Number(range[2]) };
  const parts = s.split(/[\s,]+/).filter(Boolean);
  return parts.every((x) => /^\d+$/.test(x)) ? parts.map(Number) : parts;
}
// Reads/writes item[key] directly (the value isn't a plain string, so the generic text
// spec can't drive it). `del` clears the key entirely when blank rather than leaving a
// null (keeps a saved DocumentRef/Origin free of an empty pages: line).
function pagesControl(item, key, opts = {}) {
  const input = el("input", {
    type: "text",
    class: opts.cell ? "" : "",
    placeholder: opts.placeholder || "e.g.  4 5   ·   112-114   ·   section2.1",
    oninput: (e) => {
      const v = textToPages(e.target.value);
      if (v == null) delete item[key];
      else item[key] = v;
      notifyDirty();
    },
  });
  input.value = pagesToText(item[key]);
  return input;
}
function pagesField(item, key, ctx = {}) {
  const box = el("div", ctx.cell ? {} : { class: "field-row" });
  if (!ctx.cell) box.appendChild(el("label", {}, "Pages"));
  box.appendChild(pagesControl(item, key, { cell: ctx.cell }));
  if (!ctx.cell) {
    box.appendChild(el("div", { class: "field-hint" }, "Space-separated PDF page numbers (PhysicalRef), a first–last range, or PDF bookmark names (NamedDestination). Type is inferred from the values."));
  }
  return box;
}

// A list-of-DocumentRef editor ({ref, pages, title}) - used wherever the model nests
// `list[DocumentRef]` (MethodDef.documents, CommentDef.documents). `pages`/`title` map to
// the optional def:PDFPageRef child.
function documentRefListEditor(viewKey, list) {
  return toggleableListEditor(viewKey, list, [
    { key: "ref", label: "Document", kind: "ref", hint: "A document from documents.yaml, by name." },
    { key: "pages", label: "Pages", kind: "custom", render: (item, ctx) => pagesField(item, "pages", ctx) },
    { key: "title", label: "Page-link title", kind: "text", hint: "def:PDFPageRef/@Title - an optional, more descriptive label for the page link." },
  ], {
    newItem: () => ({ ref: null }),
    addLabel: "+ Add document reference",
    summary: (item) => `${refToText(item.ref) || "(no document)"}${item.pages != null ? "  ·  p. " + pagesToText(item.pages) : ""}`,
  });
}

// Per-item collapse state, keyed by object identity rather than list index (so it
// survives reordering/insertion/removal of *other* items) and kept out of the data
// object itself (it must never end up in the JSON sent to the server). A list
// longer than COLLAPSE_DEFAULT_THRESHOLD starts collapsed - useful for a 150-variable
// dataset - a short one starts open.
const collapseState = new WeakMap();
const COLLAPSE_DEFAULT_THRESHOLD = 5;

function isCollapsed(item, list) {
  return collapseState.has(item) ? collapseState.get(item) : list.length > COLLAPSE_DEFAULT_THRESHOLD;
}

// Which field identifies an item within its list (checked in this order - the first
// one present on the item wins), and which field is its human-readable companion, per
// kind of card: Variable {name, label}, Term {code, decode}, Expression {context, -},
// StandardDef/Document/ValueListEntry/AnalysisResult {name, -}. A card with neither
// (RangeCheck: variable/comparator/values) duplicates with no prompt - nothing on it
// works as a name two entries could collide on.
const DUPLICATE_IDENTITY_FIELDS = ["name", "code", "context"];
const DUPLICATE_LABEL_FIELDS = ["label", "decode"];

function promptUniqueValue(message, suggested, existingValues) {
  let value = suggested;
  for (;;) {
    value = prompt(message, value);
    if (value === null) return null; // cancelled
    value = value.trim();
    if (!value) {
      alert("This can't be blank.");
      continue;
    }
    if (existingValues.includes(value)) {
      alert(`"${value}" is already used in this list - duplicate names collide when the file builds. Pick a different one.`);
      continue;
    }
    return value;
  }
}

// Deep-clones `item` and, if it has a name/code/context, prompts for a new one (and a
// new label/decode, if it has one) before returning it - never silently produces two
// list entries with the same identity, which would derive the same OID and hard-fail
// `define build`'s collision check. Returns null if the user cancels the identity
// prompt (a cancelled label prompt just keeps the original label).
function duplicateItem(item, list) {
  const clone = JSON.parse(JSON.stringify(item));
  const idField = DUPLICATE_IDENTITY_FIELDS.find((f) => f in item);
  if (idField) {
    const existing = list.map((i) => i[idField]).filter((v) => v !== undefined);
    const newValue = promptUniqueValue(`New ${idField} for the duplicate (must be unique in this list):`, `${item[idField]}_COPY`, existing);
    if (newValue === null) return null;
    clone[idField] = newValue;
  }
  const labelField = DUPLICATE_LABEL_FIELDS.find((f) => f in item);
  if (labelField) {
    const newLabel = prompt(`New ${labelField} for the duplicate:`, item[labelField] || "");
    if (newLabel !== null && newLabel.trim()) clone[labelField] = newLabel.trim();
  }
  return clone;
}

// A reusable "list of objects" editor: collapsible cards with a summary header, a
// remove button, and per-item fields built from `fields` (a spec array consumed by
// buildFieldFromSpec). `list` is mutated in place; card summaries are only re-read
// on add/remove/collapse-toggle, not on every keystroke, to avoid fighting
// text-input focus.
function cardListEditor(list, fields, opts) {
  const container = el("div", { class: "card-list" });
  const summary = opts.summary || ((item) => item.name || item.code || item.context || "");
  // Native HTML5 drag-and-drop: set on drag start, read (and cleared) on drop. Module-
  // scoped to this call's closure, not global, so dragging in one list can't be dropped
  // into another list's editor.
  let dragFromIdx = null;

  // Order is content here (CLAUDE.md §3: OrderNumber/KeySequence/etc. are always derived
  // from list position, never stored) - moving an item in this list is literally how a
  // user changes it, so this mutates `list` in place and marks the object dirty exactly
  // like editing any other field would.
  function moveItem(fromIdx, toIdx) {
    if (fromIdx === toIdx || fromIdx < 0 || fromIdx >= list.length || toIdx < 0 || toIdx >= list.length) return;
    const [moved] = list.splice(fromIdx, 1);
    list.splice(toIdx, 0, moved);
    notifyDirty();
    rerender();
  }

  function renderCard(item, idx) {
    const collapsed = isCollapsed(item, list);
    const card = el("div", {
      class: "expr-block",
      ondragover: (e) => {
        e.preventDefault();
        card.classList.add("drag-over");
      },
      ondragleave: () => card.classList.remove("drag-over"),
      ondrop: (e) => {
        e.preventDefault();
        card.classList.remove("drag-over");
        if (dragFromIdx !== null) moveItem(dragFromIdx, idx);
        dragFromIdx = null;
      },
    });
    const body = el("div", { hidden: collapsed || null });
    for (const spec of fields) {
      body.appendChild(buildFieldFromSpec(spec, item, { rerender }));
    }
    if (opts.extra) {
      const extra = opts.extra(item, () => (toggle.firstChild.textContent = `${collapsed ? "▸" : "▾"} ${summary(item) || `#${idx + 1}`}`));
      if (extra) body.appendChild(extra);
    }
    const toggle = el(
      "button",
      {
        type: "button",
        style: "border:none;background:none;cursor:pointer;font-weight:600;text-align:left;flex:1;padding:0;font-size:13px;",
        onclick: () => {
          collapseState.set(item, !isCollapsed(item, list));
          body.hidden = isCollapsed(item, list);
          toggle.firstChild.textContent = `${isCollapsed(item, list) ? "▸" : "▾"} ${summary(item) || `#${idx + 1}`}`;
        },
      },
      [el("span", {}, `${collapsed ? "▸" : "▾"} ${summary(item) || `#${idx + 1}`}`)]
    );
    const dragHandle = el(
      "span",
      {
        class: "drag-handle",
        draggable: "true",
        title: "Drag to reorder",
        ondragstart: (e) => {
          dragFromIdx = idx;
          e.dataTransfer.effectAllowed = "move";
        },
        ondragend: () => (dragFromIdx = null),
      },
      "⠿"
    );
    card.appendChild(
      el("div", { class: "expr-block-header" }, [
        dragHandle,
        toggle,
        el("button", { class: "row-move", type: "button", title: "Move up", disabled: idx === 0 ? "" : null, onclick: () => moveItem(idx, idx - 1) }, "▲"),
        el("button", { class: "row-move", type: "button", title: "Move down", disabled: idx === list.length - 1 ? "" : null, onclick: () => moveItem(idx, idx + 1) }, "▼"),
        el(
          "button",
          {
            class: "row-duplicate",
            type: "button",
            title: "Duplicate",
            onclick: () => {
              const copy = duplicateItem(item, list);
              if (copy === null) return; // cancelled
              collapseState.set(copy, false); // a freshly duplicated item always opens expanded
              list.splice(idx + 1, 0, copy);
              notifyDirty();
              rerender();
            },
          },
          "⧉"
        ),
        el(
          "button",
          {
            class: "row-remove",
            type: "button",
            onclick: () => {
              list.splice(idx, 1);
              notifyDirty();
              rerender();
            },
          },
          "✕ remove"
        ),
      ])
    );
    card.appendChild(body);
    return card;
  }

  function rerender() {
    clear(container);
    if (list.length > 1) {
      container.appendChild(
        el("div", { style: "margin-bottom:8px;" }, [
          el("button", { class: "secondary", type: "button", style: "font-size:11px;padding:3px 8px;margin-right:6px;", onclick: () => { list.forEach((i) => collapseState.set(i, true)); rerender(); } }, "Collapse all"),
          el("button", { class: "secondary", type: "button", style: "font-size:11px;padding:3px 8px;", onclick: () => { list.forEach((i) => collapseState.set(i, false)); rerender(); } }, "Expand all"),
        ])
      );
    }
    list.forEach((item, idx) => container.appendChild(renderCard(item, idx)));
    container.appendChild(
      el(
        "button",
        {
          class: "row-add",
          type: "button",
          onclick: () => {
            const item = opts.newItem();
            collapseState.set(item, false); // a freshly added item always opens expanded
            list.push(item);
            notifyDirty();
            rerender();
          },
        },
        opts.addLabel || "+ Add"
      )
    );
  }

  rerender();
  return container;
}

// Same list/fields/opts shape as cardListEditor - one row per item, one column per
// field, for a kind where a spreadsheet-style overview reads better than a stack of
// cards (a handful of fields each, many items: standards, documents, ...). Reuses
// duplicateItem()'s identity-uniqueness prompt and the same in-place moveItem()
// mutation cardListEditor uses, so the two layouts can't drift in what they allow.
function tableListEditor(list, fields, opts) {
  const container = el("div", { class: "table-list" });
  let dragFromIdx = null;

  function moveItem(fromIdx, toIdx) {
    if (fromIdx === toIdx || fromIdx < 0 || fromIdx >= list.length || toIdx < 0 || toIdx >= list.length) return;
    const [moved] = list.splice(fromIdx, 1);
    list.splice(toIdx, 0, moved);
    notifyDirty();
    rerender();
  }

  function renderRow(item, idx) {
    const row = el("tr", {
      class: "array-item",
      ondragover: (e) => {
        e.preventDefault();
        row.classList.add("drag-over");
      },
      ondragleave: () => row.classList.remove("drag-over"),
      ondrop: (e) => {
        e.preventDefault();
        row.classList.remove("drag-over");
        if (dragFromIdx !== null) moveItem(dragFromIdx, idx);
        dragFromIdx = null;
      },
    });
    row.appendChild(
      el("td", { class: "row-table-handle" }, [
        el("span", { class: "drag-handle", draggable: "true", title: "Drag to reorder", ondragstart: (e) => { dragFromIdx = idx; e.dataTransfer.effectAllowed = "move"; }, ondragend: () => (dragFromIdx = null) }, "⠿"),
        el("button", { class: "row-move", type: "button", title: "Move up", disabled: idx === 0 ? "" : null, onclick: () => moveItem(idx, idx - 1) }, "▲"),
        el("button", { class: "row-move", type: "button", title: "Move down", disabled: idx === list.length - 1 ? "" : null, onclick: () => moveItem(idx, idx + 1) }, "▼"),
      ])
    );
    for (const spec of fields) {
      row.appendChild(el("td", {}, buildCellFromSpec(spec, item, { rerender })));
    }
    row.appendChild(
      el("td", { class: "row-table-actions" }, [
        el(
          "button",
          {
            class: "row-duplicate",
            type: "button",
            title: "Duplicate",
            onclick: () => {
              const copy = duplicateItem(item, list);
              if (copy === null) return; // cancelled
              list.splice(idx + 1, 0, copy);
              notifyDirty();
              rerender();
            },
          },
          "⧉"
        ),
        el("button", { class: "row-remove", type: "button", title: "Remove", onclick: () => { list.splice(idx, 1); notifyDirty(); rerender(); } }, "✕"),
      ])
    );
    return row;
  }

  // opts.extra (a nested Origin editor, a where-clause/Item sub-form, ...) has no
  // column of its own - it goes in a full-width row directly under the item's row, so
  // switching views never hides something the card layout could edit. The refresh
  // callback cardListEditor passes to opts.extra (for updating a collapsed card's own
  // summary text) has no equivalent here - table rows aren't collapsible - so it's a
  // no-op; nothing currently defined uses that callback anyway.
  function renderExtraRow(item) {
    const content = opts.extra(item, () => {});
    if (!content) return null;
    return el("tr", { class: "array-item-extra" }, [el("td", { colspan: String(fields.length + 2) }, [content])]);
  }

  function rerender() {
    clear(container);
    const tbody = el("tbody", {});
    list.forEach((item, idx) => {
      tbody.appendChild(renderRow(item, idx));
      if (opts.extra) {
        const extraRow = renderExtraRow(item);
        if (extraRow) tbody.appendChild(extraRow);
      }
    });
    const table = el("table", { class: "rows" }, [
      el("thead", {}, [el("tr", {}, [el("th", {}, ""), ...fields.map((f) => el("th", {}, f.label)), el("th", {}, "")])]),
      tbody,
    ]);
    container.appendChild(table);
    container.appendChild(
      el(
        "button",
        {
          class: "row-add",
          type: "button",
          onclick: () => {
            list.push(opts.newItem());
            notifyDirty();
            rerender();
          },
        },
        opts.addLabel || "+ Add"
      )
    );
  }

  rerender();
  return container;
}

// spec: {key, label, kind: 'text'|'number'|'checkbox'|'select'|'ref'|'stringlist', options?, hint?, validate?}
// `validate(value, item)` -> null | "error" | {msg, warn:true}; wired through attachValidation.
function buildFieldFromSpec(spec, item, ctx = {}) {
  const value = get(item, spec.key);
  const onChange = (v) => set(item, spec.key, v);
  const v = spec.validate ? (x) => spec.validate(x, item) : undefined;
  switch (spec.kind) {
    case "custom":
      return spec.render(item, ctx); // returns a complete element (its own .field-row)
    case "number":
      return numberField(spec.label, value, onChange, { hint: spec.hint, validate: v });
    case "checkbox":
      return checkboxField(spec.label, value, onChange);
    case "select":
      return selectField(spec.label, value, spec.options, onChange, { ...spec, validate: v });
    case "ref":
      return refField(spec.label, value, onChange, { hint: spec.hint, validate: v, suggestions: spec.suggest ? spec.suggest(item) : undefined, onPicker: spec.picker });
    case "stringlist":
      return stringListField(spec.label, value, onChange, spec.hint);
    case "textarea":
      return textareaField(spec.label, value, onChange, { ...spec, validate: v });
    default:
      return textField(spec.label, value, onChange, { ...textOpts(spec, item, ctx), validate: v });
  }
}

// A text field spec can carry `suggest(item) -> string[]` (datalist), `disabled(item)`,
// and `onCommit(item, value)` (mutate the item, then re-render the whole list so
// sibling fields reflect it) - used by the CT-aware codelist term editor.
function textOpts(spec, item, ctx) {
  const opts = { hint: spec.hint, placeholder: spec.placeholder };
  if (spec.suggest) opts.suggestions = spec.suggest(item) || [];
  if (spec.disabled) opts.disabled = spec.disabled(item);
  if (spec.onCommit) {
    opts.onCommit = (v) => {
      set(item, spec.key, v);
      spec.onCommit(item, v);
      notifyDirty();
      if (ctx.rerender) ctx.rerender();
    };
  }
  return opts;
}

// Same field specs as buildFieldFromSpec, bare (no label/hint) - one <td> cell in
// tableListEditor's row-per-item layout, where the column header already is the label.
function buildCellFromSpec(spec, item, ctx = {}) {
  const value = get(item, spec.key);
  const onChange = (v) => set(item, spec.key, v);
  // In a table cell the column header is the only label, so an empty control shows the
  // field name as placeholder text.
  const ph = spec.label;
  let control;
  switch (spec.kind) {
    case "custom":
      return spec.render(item, { ...ctx, cell: true });
    case "number":
      control = numberControl(value, onChange, { placeholder: ph }); break;
    case "checkbox":
      return checkboxControl(value, onChange);
    case "select":
      control = selectControl(value, spec.options, onChange, { ...spec, placeholder: ph }); break;
    case "ref":
      control = refControl(value, onChange, { placeholder: ph, suggestions: spec.suggest ? spec.suggest(item) : undefined, onPicker: spec.picker }); break;
    case "stringlist":
      control = stringListControl(value, onChange, { placeholder: ph }); break;
    case "textarea":
      control = textareaControl(value, onChange, { ...spec, placeholder: ph }); break;
    default: {
      const opts = textOpts(spec, item, ctx);
      if (!opts.placeholder) opts.placeholder = ph;
      control = textControl(value, onChange, opts);
    }
  }
  if (!spec.validate) return control;
  return attachValidation(el("div", { class: "cell-wrap" }, [control]), (v) => spec.validate(v, item));
}

// ---------------------------------------------------------------------------
// Shared field specs
// ---------------------------------------------------------------------------

const VARIABLE_TYPES = [
  "text", "integer", "float", "date", "time", "datetime", "partialDate", "partialTime",
  "partialDatetime", "durationDatetime", "intervalDatetime", "incompleteDatetime",
  "incompleteDatePartialTime", "incompleteTimePartialDate", "boolean",
];

const ORIGIN_TYPES = ["Assigned", "Collected", "Derived", "Not Available", "Predecessor", "Protocol"];
const ORIGIN_SOURCES = ["Investigator", "Sponsor", "Subject", "Vendor"];

// `hints` (optional): { VARNAME: { codelist: [...], role: [...], sources: [...] } } from
// the attached standards that describe this dataset - drives the datalist on Codelist and
// Role and the "ⓘ Standard" info field.
function variableFieldSpecs(hints) {
  const entryFor = (item) => (hints && item.name ? hints[item.name.trim().toUpperCase()] : null);
  const listFor = (item, field) => {
    const h = entryFor(item);
    return h ? h[field] || [] : [];
  };
  const specs = [
    { key: "name", label: "Name", kind: "text", validate: (v) => requiredField("Name")(v) || variableNameWarnings(v) },
    {
      key: "label", label: "Label", kind: "text",
      validate: (v) => requiredField("Label")(v) || maxLenField("Label", 40)(v),
      hint: "Variable labels are capped at 40 characters in xpt v5.",
    },
    { key: "type", label: "Type", kind: "select", options: VARIABLE_TYPES, validate: requiredField("Type") },
    { key: "length", label: "Length", kind: "number" },
    { key: "significant_digits", label: "Significant Digits", kind: "number" },
    { key: "display_format", label: "Display Format", kind: "text" },
    { key: "mandatory", label: "Mandatory", kind: "checkbox" },
    { key: "role", label: "Role", kind: "text", suggest: hints ? (item) => listFor(item, "role") : undefined },
    { key: "sas_field_name", label: "SAS Field Name", kind: "text", hint: "Defaults to Name if left blank.", validate: (v) => variableNameWarnings(v) },
    {
      key: "codelist", label: "Codelist", kind: "ref",
      hint: "Reference by name, or oid:LITERAL. Double-click to search existing codelists or create a new one.",
      suggest: hints ? (item) => listFor(item, "codelist") : undefined,
      picker: (text, setValue) => openCodelistPicker(text, setValue),
    },
    {
      key: "method", label: "Method", kind: "ref",
      hint: "Reference by path under methods/ (e.g. adsl/trtsdt), or oid:LITERAL. Double-click to search existing methods or create a new one.",
      picker: (text, setValue) => openMethodPicker(text, setValue),
    },
    {
      key: "comment", label: "Comment", kind: "ref",
      hint: "Reference by path under comments/ (e.g. adsl__usubjid), or oid:LITERAL. Double-click to search existing comments or create a new one.",
      picker: (text, setValue) => openCommentPicker(text, setValue),
    },
    { key: "valuelist", label: "Value List", kind: "ref" },
    { key: "same_as", label: "Same As (alias target)", kind: "ref" },
    { key: "origin", label: "Origin", kind: "custom", render: (item, ctx) => originField(item, ctx) },
  ];
  if (hints) {
    specs.push({ key: "__standard", label: "Standard", kind: "custom", render: (item, ctx) => standardInfoField(entryFor(item), ctx) });
  }
  return specs;
}

// The "ⓘ Standard" cell/field on a variable: a chip when an attached standard describes
// it (click → overlay with every field the standard carries), nothing when it doesn't.
function standardInfoField(entry, ctx = {}) {
  const box = el("div", ctx.cell ? {} : { class: "field-row" });
  if (!ctx.cell) box.appendChild(el("label", {}, "Standard"));
  const sources = (entry && entry.sources) || [];
  if (!sources.length) {
    if (!ctx.cell) box.appendChild(el("span", { class: "field-hint" }, "not in an attached standard"));
    return box;
  }
  const s0 = sources[0];
  box.appendChild(
    el("button", {
      class: "origin-chip", type: "button", title: "Show standard definition",
      onclick: () => openStandardVariableOverlay(sources),
    }, `ⓘ ${s0.standard}/${s0.unit}${s0.template ? " (≈" + s0.name + ")" : ""}${sources.length > 1 ? "  +" + (sources.length - 1) : ""}`)
  );
  return box;
}

function openStandardVariableOverlay(sources) {
  const s0 = sources[0];
  openModal(`${s0.name} - standard definition`, () => {
    const body = el("div", {});
    for (const s of sources) {
      const rows = [
        ["Standard", `${s.standard} / ${s.unit}`],
        ["Variable", s.name + (s.template ? "  (templated - matched by digit pattern)" : "")],
        ["Label", s.label || "-"],
        ["Type", s.type || "-"],
        ["Core", s.mandatory ? "Required / Expected" : "Permissible"],
        ["Role", s.role || "- (not in this standard)"],
        ["Codelist", s.codelist || "-"],
      ];
      const tbl = el("table", { class: "rows", style: "margin-bottom:10px;" },
        rows.map(([k, v]) => el("tr", {}, [
          el("td", { style: "font-weight:600;color:var(--text-dim);white-space:nowrap;" }, k),
          el("td", {}, v),
        ]))
      );
      body.appendChild(tbl);
      if (s.description) body.appendChild(el("div", { class: "field-hint", style: "white-space:pre-wrap;margin-bottom:14px;" }, s.description.replace(/\\n/g, "\n")));
    }
    return body;
  });
}

// The Origin form's fields, no wrapper - shared by the overlay the variables/value-list
// editors open (openOriginOverlay).
function originFields(item) {
  const box = el("div", {});
  box.appendChild(selectField("Origin Type", item.origin.type, ORIGIN_TYPES, (v) => (item.origin.type = v), { required: true }));
  box.appendChild(textField("Predecessor Text (source:)", item.origin.source, (v) => (item.origin.source = v), { hint: "Predecessor origin only, e.g. DM.STUDYID." }));
  box.appendChild(textField("Description", item.origin.description, (v) => (item.origin.description = v), { hint: "Any non-Predecessor origin - free text, e.g. “EDC System”." }));
  box.appendChild(selectField("Data Source (Investigator/Sponsor/Subject/Vendor)", item.origin.data_source, ORIGIN_SOURCES, (v) => (item.origin.data_source = v)));
  box.appendChild(refField("Origin Document", item.origin.document, (v) => (item.origin.document = v), { hint: "A CRF page reference is required for a Collected origin whose Source is Investigator or Subject." }));
  box.appendChild(pagesField(item.origin, "pages"));
  box.appendChild(textField("Page-link title", item.origin.pages_title, (v) => (item.origin.pages_title = v), { hint: "def:PDFPageRef/@Title - optional descriptive label." }));
  return box;
}

// A one-line summary of what an origin says, for the chip.
function originSummary(o) {
  if (!o) return "";
  const bits = [o.type || "?"];
  if (o.source) bits.push(o.source);
  else if (o.description) bits.push(o.description);
  if (o.data_source) bits.push(o.data_source);
  const doc = refToText(o.document);
  if (doc) bits.push("↪ " + doc);
  return bits.join(" · ");
}

// Origin as a compact chip (a read-only view of what's set, or a dashed "+ Add origin").
// Clicking it opens the full form in an overlay - used in the variables list, where
// inlining four fields per row would drown the actual variable metadata. `ctx.cell` is
// set when this renders as a table cell (no label - the column header already is one).
function originField(item, ctx = {}) {
  const box = el("div", ctx.cell ? {} : { class: "field-row" });
  function render() {
    clear(box);
    if (!ctx.cell) box.appendChild(el("label", {}, "Origin"));
    if (!item.origin) {
      box.appendChild(el("button", {
        class: "origin-chip empty", type: "button",
        onclick: () => { item.origin = { type: "Derived" }; notifyDirty(); openOriginOverlay(item, render); },
      }, "+ Add origin"));
      return;
    }
    box.appendChild(el("button", {
      class: "origin-chip", type: "button", title: "Edit origin",
      onclick: () => openOriginOverlay(item, render),
    }, originSummary(item.origin)));
  }
  render();
  return box;
}

function openOriginOverlay(item, refresh) {
  openModal(
    `Origin - ${item.name || "variable"}`,
    (close) => {
      const body = el("div", {});
      if (item.origin) body.appendChild(originFields(item));
      body.appendChild(el("div", { style: "display:flex;gap:8px;margin-top:14px;" }, [
        el("button", { class: "primary", type: "button", onclick: close }, "Done"),
        el("button", { class: "row-remove", type: "button", onclick: () => { item.origin = null; notifyDirty(); close(); } }, "✕ remove origin"),
      ]));
      return body;
    },
    refresh
  );
}

const STANDARD_FIELDS = [
  { key: "name", label: "Name", kind: "text" },
  { key: "type", label: "Type", kind: "select", options: ["IG", "CT"], required: true },
  { key: "version", label: "Version", kind: "text" },
  { key: "publishing_set", label: "Publishing Set", kind: "text" },
  { key: "status", label: "Status", kind: "select", options: ["Final", "Draft"] },
  { key: "comment", label: "Comment", kind: "ref" },
  { key: "oid", label: "OID override", kind: "text" },
  { key: "standards_file", label: "Local CSV", kind: "text", hint: "Path in the Standards folder, e.g. data_tabulation/SDTMIG_v3.4.csv. Drives 'new dataset / codelists from standard'." },
];

// Table vs card view, per list-of-objects editor. Table is the default; a key is only
// present here once the user has toggled that list, and holds `false` when they picked
// card. Persisted the same way as the autosave preference - server.py's /api/state,
// ~/.config/defineyaml/editor-state.json (webui/state.py) - restored in boot() and
// re-saved on every toggle, so it survives a reload the same way autosave and the
// last-opened object already do. Keyed by a short string naming which list this is
// ("codelists.terms", "datasets.variables", ...), not by object kind alone, since one
// kind can have more than one list-of-objects field.
const listViewState = {};

// Whether the datasets editor's general-metadata block is collapsed to its summary row.
// In-memory only (an ordinary view preference, like sidebar collapse) - not persisted,
// not part of any save payload.
let datasetMetaCollapsed = false;

// A toggle between tableListEditor and cardListEditor over the same list/fields/opts -
// every list-of-objects editor gets one. Table view is the default (a compact grid reads
// better for the common case - many rows, a few short fields - and table view is never a
// narrower editor than card view, opts.extra dropping to a full-width row underneath);
// the user can switch any single list to cards, file-by-file, and that choice persists.
function toggleableListEditor(viewKey, list, fields, opts) {
  const wrap = el("div", {});
  const body = el("div", {});
  const toggle = el("button", { class: "secondary", type: "button", style: "font-size:11px;padding:3px 8px;margin-bottom:8px;" });
  function render() {
    const isTable = listViewState[viewKey] !== false; // absent -> table (the default)
    toggle.textContent = isTable ? "Card view" : "Table view";
    clear(body);
    body.appendChild(isTable ? tableListEditor(list, fields, opts) : cardListEditor(list, fields, opts));
  }
  toggle.onclick = () => {
    listViewState[viewKey] = listViewState[viewKey] === false; // flip, defaulting from table
    render();
    // Persisted like the autosave preference (server.py's /api/state ->
    // ~/.config/defineyaml/editor-state.json, webui/state.py) - an ordinary per-machine
    // UI preference, not submission content, so it doesn't belong in the tree itself.
    API.putEditorState({ list_views: listViewState }).catch(() => {});
  };
  wrap.appendChild(toggle);
  wrap.appendChild(body);
  render();
  return wrap;
}

// ---------------------------------------------------------------------------
// Per-kind editors. Each returns a DOM node appended into the form body.
// `working` is the full loaded object for the item (mutated in place).
// ---------------------------------------------------------------------------

// "+ Add standard from local folder" - only shown when this tree's standards_folder:
// (standards.yaml, CLAUDE.md §9.2) resolves and has files. Picking one appends a
// StandardDef pre-filled from the file's name/version (type inferred: terminology/* ->
// CT, else IG); the user tweaks the rest inline.
async function renderAddStandardFromFolder(slot, working) {
  let files;
  try {
    const cfg = await apiGet("/api/standards/config");
    if (!cfg.folder || !cfg.exists) return;
    files = await apiGet("/api/standards/files");
  } catch {
    return;
  }
  const allFiles = files.categories.flatMap((c) => c.files);
  if (!allFiles.length) return;

  const select = el("select", { style: "max-width:340px;" });
  for (const cat of files.categories) {
    const group = el("optgroup", { label: cat.category || "(root)" });
    for (const f of cat.files) {
      group.appendChild(el("option", { value: f.path }, `${f.standard || f.name}${f.version ? " " + f.version : ""}`));
    }
    select.appendChild(group);
  }
  const addBtn = el(
    "button",
    {
      class: "secondary",
      type: "button",
      style: "margin-left:6px;font-size:11px;padding:3px 8px;",
      onclick: () => {
        const f = allFiles.find((x) => x.path === select.value);
        if (!f) return;
        const isCt = (f.category || "").startsWith("terminology");
        working.standards.push({
          name: (f.standard || f.name.replace(/\.csv$/i, "")).trim(),
          type: isCt ? "CT" : "IG",
          version: (f.version || "").replace(/^v/i, ""),
          status: "Final",
          standards_file: f.path,
        });
        notifyDirty();
        renderEditor();
      },
    },
    "Add"
  );
  const panel = el("div", { hidden: true, style: "margin-top:6px;" }, [select, addBtn]);
  const link = el("button", { class: "row-add", type: "button", onclick: () => (panel.hidden = !panel.hidden) }, "+ Add standard from local folder");
  slot.appendChild(link);
  slot.appendChild(panel);
}

// C66788 "CodeList Dictionary Name" values for the ExternalCodeList Dictionary field -
// fetched once per session (the local CT CSVs don't change mid-edit). Empty array when
// no CT is attached; the field stays free-text either way.
let externalDictNamesCache = null;
async function ensureExternalDictNames() {
  if (externalDictNamesCache) return externalDictNamesCache;
  try {
    externalDictNamesCache = (await apiGet("/api/standards/external-dictionaries")).names || [];
  } catch {
    externalDictNamesCache = [];
  }
  return externalDictNamesCache;
}

// The codelist term editor, CT-aware. When an attached CT standards_file (CLAUDE.md
// §9.2) has this codelist (matched by its C-code, then its submission value), its terms
// drive: datalist suggestions on Code/Decode, auto-fill of the rest of a row when a
// standard code is entered, and - for a code that isn't in the standard - a blanked,
// disabled NCI Code plus an auto-ticked per-term Extended (def:ExtendedValue). Existing
// rows are aligned to the standard once on open (marking the object dirty). With no CT
// file attached it's the plain Code / Decode / NCI Code / Extended editor.
//
// opts.withDecode (default true): false for an EnumeratedItem codelist (coded values with
// no Decode) - the Decode column and its CT auto-fill are dropped.
async function renderCodelistTerms(host, working, opts = {}) {
  const withDecode = opts.withDecode !== false;
  if (!working.terms) working.terms = [];
  clear(host);
  host.appendChild(el("div", { class: "field-hint" }, "Checking attached CT…"));

  let ref = { found: false, terms: [] };
  try {
    const params = new URLSearchParams();
    if (working.name) params.set("name", working.name);
    if (working.nci_code) params.set("nci_code", working.nci_code);
    ref = await apiGet(`/api/standards/scaffold/ct-codelist?${params.toString()}`);
  } catch {
    /* no CT folder configured, or lookup failed - fall through to the plain editor */
  }
  clear(host);

  const refTerms = ref.found ? ref.terms : [];
  // CT term codes (CodedValue) are case-sensitive - "PA" and "Pa" are different values -
  // so match them exactly (whitespace-trimmed only). Decodes are human labels, matched
  // loosely on purpose.
  const ckey = (c) => (c || "").trim();
  const byCode = new Map(refTerms.map((t) => [ckey(t.code), t]));
  const byDecode = new Map(refTerms.filter((t) => t.decode).map((t) => [t.decode.trim().toLowerCase(), t]));
  const hasCt = !!ref.found;
  const inCt = (code) => !!ckey(code) && byCode.has(ckey(code));

  if (hasCt) {
    let changed = 0;
    for (const t of working.terms) {
      const m = t.code ? byCode.get(ckey(t.code)) : null;
      if (m) {
        if (!t.nci_code && m.nci_code) { t.nci_code = m.nci_code; changed++; }
        if (t.extended) { delete t.extended; changed++; }
      } else if (t.code && t.code.trim()) {
        if (t.nci_code) { delete t.nci_code; changed++; }
        if (!t.extended) { t.extended = true; changed++; }
      }
    }
    if (changed) {
      notifyDirty();
      showStatus(true, `Aligned ${changed} field(s) to ${ref.standard} CT - review, then save.`);
    }
    host.appendChild(
      el("div", { class: "field-hint", style: "margin-bottom:6px;" },
        `Standard CT: ${ref.standard} · ${ref.value} (${refTerms.length} terms${ref.extensible ? ", extensible" : ""}). A Code not in it is auto-flagged Extended with NCI Code cleared.`)
    );
  }

  // A term's `code` is its CodedValue - two CodeListItems with the same one is invalid
  // Define-XML that P21 flags. Case-sensitive ("PA" != "Pa"), whitespace-trimmed. The last
  // accepted code per term lets a duplicate entry revert rather than just blank.
  const goodCode = new WeakMap();
  for (const t of working.terms) goodCode.set(t, ckey(t.code));
  const codeClashes = (item, v) =>
    !!ckey(v) && working.terms.some((t) => t !== item && ckey(t.code) === ckey(v));

  const applyStandardFill = (item, v) => {
    if (!hasCt) return;
    const m = v ? byCode.get(ckey(v)) : null;
    if (m) {
      if (withDecode && m.decode != null && m.decode !== "") item.decode = m.decode;
      if (m.nci_code) item.nci_code = m.nci_code;
      else delete item.nci_code;
      delete item.extended;
    } else if (v && v.trim()) {
      delete item.nci_code;
      item.extended = true;
    }
  };
  const commitCode = (item, v) => {
    if (codeClashes(item, v)) {
      alert(`A term with code "${(v || "").trim()}" is already in this codelist. Codes must be unique.`);
      item.code = goodCode.get(item) || null;
      return;
    }
    goodCode.set(item, ckey(v));
    applyStandardFill(item, v);
  };
  const applyDecode = (item, v) => {
    if (!hasCt || !v || !v.trim()) return;
    const m = byDecode.get(v.trim().toLowerCase());
    if (!m) return;
    if (codeClashes(item, m.code)) {
      alert(`Decode "${v.trim()}" maps to code "${m.code}", already in this codelist - not applied.`);
      return;
    }
    item.code = m.code;
    goodCode.set(item, ckey(m.code));
    if (m.nci_code) item.nci_code = m.nci_code;
    delete item.extended;
  };

  // @Rank - "numeric significance relative to the other items"; NOT display order (that's
  // OrderNumber, always the row position). Optional, but all-or-none across the codelist
  // and distinct when set (EnumeratedCodeList._check_ranks enforces it at save; this is the
  // live visual nudge). Recomputed from the whole list, not just this row's value.
  const rankValidate = () => {
    const rs = working.terms.map((t) => t.rank);
    const setv = rs.filter((r) => r !== null && r !== undefined && r !== "");
    if (setv.length && setv.length !== rs.length) return { warn: true, msg: "Rank: set it on every term, or none." };
    if (new Set(setv.map(Number)).size !== setv.length) return { warn: true, msg: "Rank values must be distinct." };
    return null;
  };

  const specs = [
    { key: "code", label: "Code", kind: "text", suggest: () => refTerms.map((t) => t.code), onCommit: commitCode },
  ];
  if (withDecode) {
    specs.push({
      key: "decode", label: "Decode", kind: "text",
      suggest: () => refTerms.filter((t) => t.decode).map((t) => t.decode), onCommit: hasCt ? applyDecode : undefined,
    });
  }
  specs.push(
    { key: "rank", label: "Rank", kind: "number", hint: "Optional ranking key - not display order. All terms or none; distinct.", validate: rankValidate },
    { key: "nci_code", label: "NCI Code", kind: "text", disabled: hasCt ? (item) => !!item.code && !inCt(item.code) : undefined },
    { key: "extended", label: "Extended (this term is beyond the standard)", kind: "checkbox" }
  );

  host.appendChild(
    toggleableListEditor("codelists.terms", working.terms, specs, {
      newItem: () => (withDecode ? { code: "", decode: "" } : { code: "" }),
      addLabel: "+ Add term",
      summary: (item) => `${item.code || "(new)"}${withDecode && item.decode ? " - " + item.decode : ""}${item.rank != null && item.rank !== "" ? "  ·  rank " + item.rank : ""}${item.extended ? "  ·  extended" : ""}`,
    })
  );
}

// The datasets editor's variables list. Renders immediately, then - if the dataset
// corresponds to a unit in one of the attached IG standards (CLAUDE.md §9.2) - re-renders
// with datalist hints on the Codelist and Role fields drawn from that standard.
async function renderDatasetVariables(host, working) {
  if (!working.variables) working.variables = [];
  clear(host);
  const listBox = el("div", {});
  const note = el("div", { class: "field-hint", style: "margin:2px 0 6px;" }, "");
  host.appendChild(note);
  host.appendChild(listBox);

  const build = (hints) => {
    clear(listBox);
    listBox.appendChild(
      toggleableListEditor("datasets.variables", working.variables, variableFieldSpecs(hints), {
        newItem: () => ({ name: "", label: "", type: "text", mandatory: false }),
        addLabel: "+ Add variable",
      })
    );
  };
  build(null);

  const sel = state.selection;
  if (!sel || state.isNew || sel.kind !== "datasets") return;
  try {
    const res = await apiGet(`/api/standards/scaffold/variable-hints?dataset=${encodeKey(sel.key)}`);
    const vars = (res && res.variables) || {};
    if (res && res.matched && res.matched.length && Object.keys(vars).length) {
      const hv = Object.values(vars);
      const has = (f) => hv.some((h) => (h[f] || []).length);
      const fields = [has("codelist") && "Codelist", has("role") && "Role"].filter(Boolean);
      const where = res.matched.map((m) => `${m.standard} / ${m.unit}`).join(", ");
      note.textContent =
        `Matches ${where}. ` +
        (fields.length
          ? `${fields.join(" and ")} suggest standard values; `
          : `no codelist/role values in this standard to suggest (ADaM IGs have no Role column); `) +
        `each described variable gets an ⓘ Standard link.`;
      build(vars);
    }
  } catch {
    /* no standards folder / no match - the plain list stays */
  }
}

// "+ Add variable(s) from standards" - a filterable overlay over every variable of every
// attached IG standard. `existingNames` is a Set; `onAdd(cleanVariableDicts[])` appends
// the picked variables to the working dataset (client-side, like "+ Add variable").
function openAddVariablesFromStandardsModal(existingNames, onAdd) {
  let close = () => {};
  const selected = new Map(); // "std unit name" -> clean variable dict
  const filters = { standard: "", unit: "", q: "" };
  let catalog = { standards: [] };

  const stdSelect = el("select", {}, [el("option", { value: "" }, "All standards")]);
  const unitSelect = el("select", {}, [el("option", { value: "" }, "All datasets / structures")]);
  const searchInput = el("input", { type: "text", placeholder: "Search name, label or description…" });
  const listBox = el("div", { style: "margin:10px 0;max-height:340px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;padding:8px 10px;" });
  const countLine = el("div", { class: "field-hint" }, "");
  const addBtn = el("button", { class: "primary", type: "button", disabled: "" }, "Add variables");

  const cleanVar = (v) => {
    const out = { name: v.name, label: v.label || "", type: v.type || "text", mandatory: !!v.mandatory };
    // the standard's SAS field name is the variable name - but not for a templated name
    // (SITEGRy, TRTxxP), which the user will rename; blank then just tracks the new name.
    if (v.name === v.name.toUpperCase()) out.sas_field_name = v.name;
    if (v.role) out.role = v.role;
    if (v.codelist) out.codelist = v.codelist;
    return out;
  };
  const rowKey = (v) => `${v.standard} ${v.unit} ${v.name}`;

  function refreshAddBtn() {
    addBtn.disabled = selected.size === 0;
    addBtn.textContent = selected.size ? `Add ${selected.size} variable${selected.size === 1 ? "" : "s"}` : "Add variables";
  }

  function fillUnitSelect() {
    const chosen = catalog.standards.filter((s) => !filters.standard || s.name === filters.standard);
    const units = new Map();
    for (const s of chosen) for (const u of s.units || []) units.set(u.unit, (units.get(u.unit) || 0) + u.variable_count);
    unitSelect.innerHTML = "";
    unitSelect.appendChild(el("option", { value: "" }, "All datasets / structures"));
    for (const u of [...units.keys()].sort()) unitSelect.appendChild(el("option", { value: u }, `${u} (${units.get(u)})`));
    if ([...units.keys()].includes(filters.unit)) unitSelect.value = filters.unit;
    else filters.unit = "";
  }

  let searchSeq = 0;
  async function runSearch() {
    const seq = ++searchSeq;
    clear(listBox);
    listBox.appendChild(loadingBlock("Searching…"));
    const params = new URLSearchParams();
    if (filters.standard) params.set("standard", filters.standard);
    if (filters.unit) params.set("unit", filters.unit);
    if (filters.q.trim()) params.set("q", filters.q.trim());
    let res;
    try {
      res = await apiGet(`/api/standards/scaffold/ig-variables?${params.toString()}`);
    } catch (err) {
      if (seq !== searchSeq) return;
      clear(listBox);
      listBox.appendChild(el("div", { class: "field-hint" }, describeError(err)));
      return;
    }
    if (seq !== searchSeq) return;
    renderResults(res);
  }

  function renderResults(res) {
    clear(listBox);
    const vars = res.variables || [];
    countLine.textContent = `${vars.length}${res.truncated ? "+ (narrow the filters)" : ""} variable(s) match` + (selected.size ? ` · ${selected.size} selected` : "");
    if (!vars.length) {
      listBox.appendChild(el("div", { class: "field-hint" }, "Nothing matches these filters."));
      return;
    }
    listBox.appendChild(
      el("div", { style: "margin-bottom:6px;" }, [
        el("button", {
          class: "secondary", type: "button", style: "font-size:11px;padding:3px 8px;margin-right:6px;",
          onclick: () => { for (const v of vars) if (!existingNames.has(v.name)) selected.set(rowKey(v), cleanVar(v)); renderResults(res); refreshAddBtn(); },
        }, "Select all shown"),
        el("button", {
          class: "secondary", type: "button", style: "font-size:11px;padding:3px 8px;",
          onclick: () => { for (const v of vars) selected.delete(rowKey(v)); renderResults(res); refreshAddBtn(); },
        }, "Deselect shown"),
      ])
    );
    for (const v of vars) {
      const exists = existingNames.has(v.name);
      const cb = el("input", {
        type: "checkbox", disabled: exists ? "" : null,
        onchange: (e) => { if (e.target.checked) selected.set(rowKey(v), cleanVar(v)); else selected.delete(rowKey(v)); countLine.textContent = `${vars.length}${res.truncated ? "+" : ""} variable(s) match · ${selected.size} selected`; refreshAddBtn(); },
      });
      cb.checked = selected.has(rowKey(v));
      listBox.appendChild(
        el("label", { style: `display:flex;gap:8px;padding:3px 0;font-size:13px;align-items:baseline;${exists ? "color:var(--text-dim);" : ""}` }, [
          cb,
          el("div", {}, [
            el("span", { style: "font-family:var(--mono);font-weight:600;" }, v.name),
            el("span", { style: "color:var(--text-dim);" }, `  ${v.standard}/${v.unit}${v.mandatory ? " · required" : ""}${v.codelist ? " · CL " + v.codelist : ""}${v.role ? " · " + v.role : ""}`),
            v.label ? el("div", { style: "color:var(--text-dim);font-size:12px;" }, v.label) : null,
            v.description ? el("div", { style: "color:var(--text-dim);font-size:11px;margin-top:1px;" }, v.description.length > 200 ? v.description.slice(0, 200) + "…" : v.description) : null,
            exists ? el("span", { class: "orphan-badge", style: "background:var(--bg-alt);color:var(--text-dim);" }, "already in this dataset") : null,
          ]),
        ])
      );
    }
  }

  stdSelect.onchange = () => { filters.standard = stdSelect.value; fillUnitSelect(); runSearch(); };
  unitSelect.onchange = () => { filters.unit = unitSelect.value; runSearch(); };
  let debounce = null;
  searchInput.oninput = () => { filters.q = searchInput.value; clearTimeout(debounce); debounce = setTimeout(runSearch, 250); };

  addBtn.onclick = () => {
    const added = [...selected.values()].filter((v) => !existingNames.has(v.name));
    close();
    if (added.length) {
      onAdd(added);
      showStatus(true, `Added ${added.length} variable${added.length === 1 ? "" : "s"} from standards - review types/codelists, then save.`);
    }
  };

  const body = el("div", {});
  body.appendChild(el("div", { class: "two-col" }, [fieldRow("Standard", stdSelect), fieldRow("Dataset / structure", unitSelect)]));
  body.appendChild(fieldRow("Search", searchInput));
  body.appendChild(countLine);
  body.appendChild(listBox);
  body.appendChild(el("div", { style: "display:flex;justify-content:flex-end;gap:8px;margin-top:14px;" }, [
    el("button", { class: "secondary", type: "button", onclick: () => close() }, "Cancel"),
    addBtn,
  ]));

  clear(listBox);
  listBox.appendChild(loadingBlock("Loading standards…"));
  apiGet("/api/standards/scaffold/ig-catalog")
    .then((cat) => {
      catalog = cat || { standards: [] };
      if (!catalog.standards.length) {
        clear(listBox);
        listBox.appendChild(el("div", { class: "field-hint" }, "No standard has an IG CSV attached. Add one in Standards → Local CSV."));
        return;
      }
      for (const s of catalog.standards) stdSelect.appendChild(el("option", { value: s.name }, s.name));
      fillUnitSelect();
      runSearch();
    })
    .catch((err) => { clear(listBox); listBox.appendChild(el("div", { class: "field-hint" }, describeError(err))); });

  close = openModal("Add variables from standards", (c) => { close = c; return body; });
}

const EDITORS = {
  study(working) {
    const wrap = el("div", {});
    const creationField = textField(
      "Creation Date/Time",
      working.odm.creation_datetime,
      (v) => (working.odm.creation_datetime = v),
      { hint: "If empty - the define tree's latest modification is written as CreationDateTime when define.xml / define.html is generated (git history when the tree is version-controlled, otherwise the newest YAML file's timestamp)." },
    );
    // Ghost/placeholder = the value an empty field would build with right now.
    apiGet("/api/tree/last-modified")
      .then((r) => {
        if (!r || !r.datetime) return;
        const input = creationField.querySelector("input");
        if (input) input.placeholder = r.datetime;
      })
      .catch(() => {});
    wrap.appendChild(el("fieldset", {}, [
      el("legend", {}, "ODM Header"),
      textField("File OID", working.odm.file_oid, (v) => (working.odm.file_oid = v)),
      creationField,
      textField("As-Of Date/Time", working.odm.as_of_datetime, (v) => (working.odm.as_of_datetime = v)),
      textField("Originator", working.odm.originator, (v) => (working.odm.originator = v)),
      textField("Source System", working.odm.source_system, (v) => (working.odm.source_system = v)),
      textField("Source System Version", working.odm.source_system_version, (v) => (working.odm.source_system_version = v)),
      textField("Stylesheet href", working.odm.stylesheet, (v) => (working.odm.stylesheet = v), { hint: "Path to define2-1.xsl, e.g. ../stylesheets/define2-1.xsl. Leave blank to omit." }),
    ]));
    wrap.appendChild(el("fieldset", {}, [
      el("legend", {}, "Study"),
      textField("OID", working.study.oid, (v) => (working.study.oid = v)),
      textField("Name", working.study.name, (v) => (working.study.name = v)),
      textField("Description", working.study.description, (v) => (working.study.description = v)),
      textField("Protocol Name", working.study.protocol_name, (v) => (working.study.protocol_name = v)),
    ]));
    wrap.appendChild(el("fieldset", {}, [
      el("legend", {}, "Metadata Version"),
      textField("OID", working.metadata_version.oid, (v) => (working.metadata_version.oid = v)),
      textField("Name", working.metadata_version.name, (v) => (working.metadata_version.name = v)),
      textField("Description", working.metadata_version.description, (v) => (working.metadata_version.description = v)),
      textField("Define Version", working.metadata_version.define_version, (v) => (working.metadata_version.define_version = v)),
    ]));
    wrap.appendChild(stringListField("Expression Contexts", working.expression_contexts, (v) => (working.expression_contexts = v), 'Permitted FormalExpression/ProgrammingCode Context values, e.g. "SAS 9.4, R 4.4".'));
    return wrap;
  },

  standards(working) {
    if (!working.standards) working.standards = [];
    const wrap = el("div", {});
    const statusLine = el("div", { class: "field-hint", style: "margin:2px 0 10px;" }, "");
    wrap.appendChild(
      textField(
        "Local CSV standards folder",
        working.standards_folder,
        (v) => (working.standards_folder = v),
        { hint: "Folder of CDISC CSV exports this tree's standards_file: paths are relative to. Absolute, or relative to the define/ tree. Stored in this standards.yaml - save to apply." }
      )
    );
    wrap.appendChild(statusLine);
    const createSlot = el("div", { style: "margin:0 0 10px;" });
    wrap.appendChild(createSlot);
    const importSlot = el("div", { style: "margin-bottom:8px;" });
    wrap.appendChild(importSlot);
    const opts = { newItem: () => ({ name: "", type: "IG", version: "", status: "Final" }), addLabel: "+ Add standard" };
    wrap.appendChild(toggleableListEditor("standards", working.standards, STANDARD_FIELDS, opts));
    // Live status reflects the *saved* standards.yaml (the server resolves it), so it
    // catches up after Save rather than while typing.
    const refreshFolderStatus = () => {
      clear(createSlot);
      apiGet("/api/standards/config")
        .then(async (cfg) => {
          if (!cfg.folder) { statusLine.textContent = "No folder set - 'Add standard from local folder' and CSV scaffolding are unavailable."; return; }
          if (!cfg.exists) {
            statusLine.textContent = `⚠ ${cfg.error || "folder does not resolve"} (${cfg.folder})`;
            if (cfg.creatable) {
              const btn = el("button", { class: "secondary", type: "button", style: "font-size:12px;padding:4px 10px;" }, "Create this folder");
              btn.onclick = async () => {
                btn.disabled = true;
                btn.textContent = "Creating…";
                try {
                  await apiSend("POST", "/api/standards/config/create-folder");
                  showStatus(true, "Standards folder created");
                  refreshFolderStatus();
                  renderAddStandardFromFolder(importSlot, working);
                } catch (err) {
                  btn.disabled = false;
                  btn.textContent = "Create this folder";
                  showStatus(false, describeError(err));
                }
              };
              createSlot.appendChild(btn);
            }
            return;
          }
          try {
            const files = await apiGet("/api/standards/files");
            const n = files.categories.reduce((a, c) => a + c.files.length, 0);
            statusLine.textContent = `✓ ${cfg.resolved} - ${n} CSV file(s)`;
          } catch {
            statusLine.textContent = `✓ ${cfg.resolved}`;
          }
        })
        .catch(() => {});
    };
    refreshFolderStatus();
    renderAddStandardFromFolder(importSlot, working);
    return wrap;
  },

  documents(working) {
    if (!working.documents) working.documents = [];
    const wrap = el("div", {});
    wrap.appendChild(el("h3", { style: "font-size:13px;margin:0 0 4px;" }, "Documents"));
    wrap.appendChild(toggleableListEditor("documents.documents", working.documents, [
      { key: "name", label: "Name", kind: "text" },
      { key: "href", label: "Href", kind: "text" },
      { key: "title", label: "Title", kind: "text" },
      { key: "oid", label: "OID override", kind: "text" },
    ], { newItem: () => ({ name: "", href: "", title: "" }), addLabel: "+ Add document" }));
    wrap.appendChild(stringListField("Annotated CRF", working.annotated_crf, (v) => (working.annotated_crf = v), "Names of documents above, comma-separated."));
    wrap.appendChild(stringListField("Supplemental Docs", working.supplemental_docs, (v) => (working.supplemental_docs = v), "Names of documents above, comma-separated."));
    return wrap;
  },

  datasets(working) {
    const wrap = el("div", {});

    // General dataset metadata - collapses to a one-line summary so the variables list
    // below gets the room. Collapse state is module-level, so it stays put across
    // autosaves and carries to the next dataset you open.
    const meta = el("div", { hidden: datasetMetaCollapsed || null });
    meta.appendChild(el("div", { class: "two-col" }, [
      textField("Name", working.name, (v) => (working.name = v), { validate: requiredField("Name") }),
      textField("Label", working.label, (v) => (working.label = v), {
        validate: (v) => requiredField("Label")(v) || maxLenField("Label", 40)(v),
        hint: "Dataset labels are capped at 40 characters in xpt v5.",
      }),
    ]));
    meta.appendChild(el("div", { class: "two-col" }, [
      textField("Class", working.class, (v) => (working.class = v), { validate: requiredField("Class") }),
      textField("Structure", working.structure, (v) => (working.structure = v), { validate: requiredField("Structure") }),
    ]));
    meta.appendChild(el("div", { class: "two-col" }, [
      selectField("Purpose", working.purpose, ["Analysis", "Tabulation"], (v) => (working.purpose = v)),
      textField("Domain (SDTM)", working.domain, (v) => (working.domain = v)),
    ]));
    meta.appendChild(el("div", { class: "two-col" }, [
      checkboxField("Repeating", working.repeating, (v) => (working.repeating = v)),
      checkboxField("Is Reference Data", working.is_reference_data, (v) => (working.is_reference_data = v)),
    ]));
    meta.appendChild(el("div", { class: "two-col" }, [
      refField("Standard", working.standard, (v) => (working.standard = v)),
      refField("Comment", working.comment, (v) => (working.comment = v)),
    ]));
    meta.appendChild(stringListField("Keys", working.keys, (v) => (working.keys = v)));

    const leafBox = el("div", {});
    function renderLeaf() {
      clear(leafBox);
      if (!working.leaf) {
        leafBox.appendChild(el("button", { class: "row-add", type: "button", onclick: () => { working.leaf = { href: "" }; notifyDirty(); renderLeaf(); } }, "+ Add file (leaf)"));
        return;
      }
      leafBox.appendChild(el("div", { class: "two-col" }, [
        textField("Href", working.leaf.href, (v) => (working.leaf.href = v)),
        textField("Title", working.leaf.title, (v) => (working.leaf.title = v), { hint: "Defaults to the href basename." }),
      ]));
      leafBox.appendChild(el("button", { class: "row-remove", type: "button", onclick: () => { working.leaf = null; notifyDirty(); renderLeaf(); } }, "✕ remove file"));
    }
    renderLeaf();
    meta.appendChild(el("fieldset", {}, [el("legend", {}, "File (def:leaf)"), leafBox]));

    const metaSummary = () => {
      const bits = [];
      if (working.class) bits.push(working.class);
      if (working.structure) bits.push(working.structure);
      if (working.purpose) bits.push(working.purpose);
      if (working.domain) bits.push("domain " + working.domain);
      if (refToText(working.standard)) bits.push(refToText(working.standard));
      if (working.keys && working.keys.length) bits.push("keys: " + working.keys.join(", "));
      if (working.leaf && working.leaf.href) bits.push(working.leaf.href);
      return bits.join("  ·  ") || "no metadata set yet";
    };
    const chevron = el("span", {}, datasetMetaCollapsed ? "▸" : "▾");
    const summarySpan = el("span", { class: "section-collapse-summary" }, datasetMetaCollapsed ? metaSummary() : "");
    wrap.appendChild(el("button", {
      class: "section-collapse", type: "button", title: "Show/hide dataset metadata",
      onclick: () => {
        datasetMetaCollapsed = !datasetMetaCollapsed;
        meta.hidden = datasetMetaCollapsed;
        chevron.textContent = datasetMetaCollapsed ? "▸" : "▾";
        summarySpan.textContent = datasetMetaCollapsed ? metaSummary() : "";
      },
    }, [chevron, el("span", {}, "Dataset metadata"), summarySpan]));
    wrap.appendChild(meta);

    if (!working.variables) working.variables = [];
    wrap.appendChild(el("h3", { style: "font-size:13px;margin:18px 0 4px;" }, "Variables"));
    const varsHost = el("div", {});
    wrap.appendChild(varsHost);
    renderDatasetVariables(varsHost, working);

    const actionRow = el("div", { style: "margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;" });
    actionRow.appendChild(
      el("button", {
        class: "secondary", type: "button",
        onclick: () => openAddVariablesFromStandardsModal(
          new Set(working.variables.map((v) => v.name)),
          (added) => {
            for (const v of added) working.variables.push(v);
            notifyDirty();
            renderDatasetVariables(varsHost, working);
          }
        ),
      }, "+ Add variable(s) from standards")
    );
    // Copying writes straight to disk server-side (webui/copy_variables.py), so the
    // in-memory `working` here would go stale the instant it succeeds - re-fetching via
    // selectItem() rather than patching `working` locally is what picks up the result.
    actionRow.appendChild(
      copyVariablesButton(
        state.selection.key,
        () => new Set(working.variables.map((v) => v.name)),
        () => selectItem("datasets", state.selection.key)
      )
    );
    wrap.appendChild(actionRow);
    return wrap;
  },

  codelists(working) {
    const wrap = el("div", {});
    wrap.appendChild(el("div", { class: "two-col" }, [
      textField("Name", working.name, (v) => (working.name = v)),
      textField("Label", working.label, (v) => (working.label = v)),
    ]));
    wrap.appendChild(selectField("Data Type", working.type, ["text", "integer", "float"], (v) => (working.type = v)));

    // Define-XML's three CodeList shapes. The model discriminates the first two purely on
    // whether the terms carry Decode (EnumeratedCodeList._check_decode_uniform); "external"
    // is the ExternalCodeListDef branch (has `external:`, no terms).
    const KIND_LABELS = {
      decoded: "Coded values with Decode (CodeListItem)",
      enumerated: "Coded values only, no Decode (EnumeratedItem)",
      external: "External dictionary reference (ExternalCodeList)",
    };
    const KIND_BY_LABEL = Object.fromEntries(Object.entries(KIND_LABELS).map(([k, v]) => [v, k]));
    const currentKind = () => {
      if (working.external != null) return "external";
      const t = working.terms || [];
      return t.length ? (t[0].decode != null ? "decoded" : "enumerated") : "decoded";
    };

    function switchKind(next) {
      const cur = currentKind();
      if (next === cur) return;
      const losingTerms = cur !== "external" && next === "external" && (working.terms || []).length;
      const losingDecodes = cur === "decoded" && next === "enumerated" && (working.terms || []).some((t) => t.decode);
      if (losingTerms && !confirm("Switching to an external dictionary discards this codelist's terms. Continue?")) return renderEditor();
      if (losingDecodes && !confirm("Switching to EnumeratedItem drops every term's Decode value. Continue?")) return renderEditor();
      if (next === "external") {
        for (const k of ["terms", "extended", "standard", "sas_format_name", "comment", "nci_code", "aliases"]) delete working[k];
        working.external = { dictionary: "", version: "" };
      } else {
        delete working.external;
        working.terms = working.terms || [];
        for (const t of working.terms) {
          if (next === "decoded" && t.decode == null) t.decode = "";
          if (next === "enumerated") delete t.decode;
        }
      }
      notifyDirty();
      renderShape();
    }
    wrap.appendChild(
      selectField("Codelist kind", KIND_LABELS[currentKind()], Object.values(KIND_LABELS), (v) => switchKind(KIND_BY_LABEL[v]), {
        required: true,
        hint: "CodeListItem carries a human-readable Decode per code; EnumeratedItem is bare codes; External points at a dictionary (MedDRA, LOINC, …).",
      })
    );

    let dictNames = externalDictNamesCache || [];
    const shapeBox = el("div", {});
    function renderShape() {
      clear(shapeBox);
      if (currentKind() === "external") {
        if (!working.external) working.external = { dictionary: "", version: "" };
        shapeBox.appendChild(el("div", { class: "two-col" }, [
          textField("Dictionary", working.external.dictionary, (v) => (working.external.dictionary = v), {
            suggestions: dictNames,
            hint: dictNames.length
              ? "CDISC CT C66788 'CodeList Dictionary Name' - pick one or type your own (the codelist is extensible; a free-text value doesn't add a separate CT to define.xml)."
              : "e.g. MedDRA, LOINC, SNOMED CT, WHODrug. Attach a CT standard for a picklist.",
          }),
          textField("Version", working.external.version, (v) => (working.external.version = v)),
        ]));
      } else {
        if (!working.terms) working.terms = [];
        shapeBox.appendChild(el("div", { class: "two-col" }, [
          checkboxField("Non-standard codelist (def:IsNonStandard)", working.extended, (v) => (working.extended = v)),
          textField("NCI Code", working.nci_code, (v) => (working.nci_code = v)),
        ]));
        shapeBox.appendChild(el("div", { class: "two-col" }, [
          refField("Standard (CT version)", working.standard, (v) => (working.standard = v)),
          textField("SAS Format Name", working.sas_format_name, (v) => (working.sas_format_name = v)),
        ]));
        shapeBox.appendChild(refField("Comment", working.comment, (v) => (working.comment = v)));
        shapeBox.appendChild(el("h3", { style: "font-size:13px;margin:14px 0 4px;" }, "Terms"));
        const termsHost = el("div", {});
        shapeBox.appendChild(termsHost);
        renderCodelistTerms(termsHost, working, { withDecode: currentKind() === "decoded" });
      }
    }
    renderShape();
    wrap.appendChild(shapeBox);
    // Fill the Dictionary picklist once the C66788 lookup lands (only matters if external).
    ensureExternalDictNames().then((names) => {
      if (names && names.length && names !== dictNames) {
        dictNames = names;
        if (currentKind() === "external") renderShape();
      }
    });
    return wrap;
  },

  methods(working) {
    const wrap = el("div", {});
    wrap.appendChild(el("div", { class: "two-col" }, [
      textField("Name", working.name, (v) => (working.name = v)),
      selectField("Type", working.type, ["Computation", "Imputation", "Other"], (v) => (working.type = v)),
    ]));
    wrap.appendChild(textareaField("Description", working.description, (v) => (working.description = v), { hint: "Required whenever expressions: are present." }));
    if (!working.expressions) working.expressions = [];
    wrap.appendChild(el("h3", { style: "font-size:13px;margin:14px 0 4px;" }, "Formal Expressions"));
    wrap.appendChild(
      toggleableListEditor(
        "methods.expressions",
        working.expressions,
        [
          { key: "context", label: "Context", kind: "text", hint: 'e.g. "SAS 9.4" - must be unique per method.' },
          { key: "code", label: "Code", kind: "textarea", code: true },
        ],
        { newItem: () => ({ context: "", code: "" }), addLabel: "+ Add expression" }
      )
    );
    if (!working.documents) working.documents = [];
    wrap.appendChild(el("h3", { style: "font-size:13px;margin:14px 0 4px;" }, "Documentation references"));
    wrap.appendChild(el("div", { class: "field-hint", style: "margin-bottom:6px;" }, "Documents (with optional PDF page references) where this method is specified - e.g. an ADRG section."));
    wrap.appendChild(documentRefListEditor("methods.documents", working.documents));
    return wrap;
  },

  comments(working) {
    const wrap = el("div", {});
    wrap.appendChild(textareaField("Description", working.description, (v) => (working.description = v)));
    if (!working.documents) working.documents = [];
    wrap.appendChild(el("h3", { style: "font-size:13px;margin:14px 0 4px;" }, "Documents"));
    wrap.appendChild(documentRefListEditor("comments.documents", working.documents));
    return wrap;
  },

  whereclauses(working) {
    const wrap = el("div", {});
    wrap.appendChild(refField("Comment (required if conditions span more than one dataset)", working.comment, (v) => (working.comment = v)));
    if (!working.conditions) working.conditions = [];
    wrap.appendChild(el("h3", { style: "font-size:13px;margin:14px 0 4px;" }, "Conditions"));
    wrap.appendChild(
      toggleableListEditor(
        "whereclauses.conditions",
        working.conditions,
        [
          { key: "variable", label: "Variable", kind: "ref", hint: "DATASET.VARIABLE, or oid:LITERAL." },
          { key: "comparator", label: "Comparator", kind: "select", options: ["EQ", "NE", "LT", "LE", "GT", "GE", "IN", "NOTIN"], required: true },
          { key: "values", label: "Values", kind: "stringlist", hint: "More than one value requires IN or NOTIN." },
        ],
        { newItem: () => ({ variable: "", comparator: "EQ", values: [] }), addLabel: "+ Add condition", summary: (item) => `${refToText(item.variable) || "?"} ${item.comparator || ""} ${(item.values || []).join(",")}` }
      )
    );
    return wrap;
  },

  valuelists(working) {
    const wrap = el("div", {});
    wrap.appendChild(el("div", { class: "two-col" }, [
      textField("Dataset", working.dataset, (v) => (working.dataset = v)),
      textField("Variable", working.variable, (v) => (working.variable = v)),
    ]));
    if (!working.entries) working.entries = [];
    wrap.appendChild(el("h3", { style: "font-size:13px;margin:14px 0 4px;" }, "Entries"));
    wrap.appendChild(
      toggleableListEditor(
        "valuelists.entries",
        working.entries,
        [{ key: "name", label: "Entry Name", kind: "text" }, { key: "comment", label: "Join Comment (cross-dataset where)", kind: "ref" }],
        {
          newItem: () => ({ name: "", where: "", item: { name: "", label: "", type: "text", mandatory: false } }),
          addLabel: "+ Add entry",
          extra: (item) => {
            const box = el("div", {});
            if (Array.isArray(item.where)) {
              box.appendChild(el("div", { class: "field-hint" }, "where: is an inline condition list - edit it via Raw JSON below; the structured editor only offers a named reference here."));
            } else {
              box.appendChild(refField("Where (named where clause)", item.where, (v) => (item.where = v)));
            }
            box.appendChild(el("fieldset", {}, [el("legend", {}, "Item"), ...variableFieldSpecs().map((spec) => buildFieldFromSpec(spec, item.item))]));
            return box;
          },
        }
      )
    );
    return wrap;
  },

  analysis_results(working) {
    const wrap = el("div", {});
    wrap.appendChild(el("div", { class: "two-col" }, [
      textField("Name", working.name, (v) => (working.name = v)),
      textField("Title", working.title, (v) => (working.title = v)),
    ]));
    wrap.appendChild(refField("Document", working.document && working.document.ref, (v) => (working.document = { ...(working.document || {}), ref: v }), "The submitted output document (e.g. a TFL)."));
    if (!working.results) working.results = [];
    wrap.appendChild(el("h3", { style: "font-size:13px;margin:14px 0 4px;" }, "Results"));
    wrap.appendChild(
      toggleableListEditor(
        "analysis_results.results",
        working.results,
        [
          { key: "name", label: "Name", kind: "text" },
          { key: "description", label: "Description", kind: "textarea" },
          { key: "parameter", label: "Parameter", kind: "ref" },
          { key: "reason", label: "Analysis Reason", kind: "text", hint: "e.g. SPECIFIED IN PROTOCOL, SPECIFIED IN SAP, DATA DRIVEN, REQUESTED BY REGULATORY AGENCY (extensible)." },
          { key: "purpose", label: "Analysis Purpose", kind: "text", hint: "e.g. PRIMARY OUTCOME MEASURE, SECONDARY OUTCOME MEASURE, EXPLORATORY OUTCOME MEASURE (extensible)." },
          { key: "join_comment", label: "Join Comment", kind: "ref", hint: "Required when datasets span more than one dataset." },
        ],
        {
          newItem: () => ({ name: "", description: "", reason: "", purpose: "", datasets: [] }),
          addLabel: "+ Add result",
          extra: (item) => {
            if (!item.datasets) item.datasets = [];
            const box = el("div", {});
            box.appendChild(el("div", { class: "field-hint", style: "margin-bottom:6px;" }, "datasets:, documentation: and programming_code: are edited via Raw JSON below - save this card once, then use the object's Raw JSON toggle."));
            return box;
          },
        }
      )
    );
    return wrap;
  },
};

// ---------------------------------------------------------------------------
// "Used by" / orphan panel
// ---------------------------------------------------------------------------

function kindLabel(kind) {
  const meta = state.kinds.find((k) => k.kind === kind);
  return meta ? meta.label : kind;
}

function renderUsagesPanel(usagesData) {
  if (!usagesData) {
    return el("div", { class: "field-hint", style: "margin-bottom:14px;" }, "Usages unavailable.");
  }
  if (usagesData.used_by.length === 0) {
    return el("div", { class: "usages-panel usages-empty" }, [
      el("span", { class: "orphan-badge" }, "unused"),
      " Nothing else in the tree references this - best-effort (a literal {oid: ...} reference wouldn't be detected).",
    ]);
  }
  // Group by referencing kind so e.g. five variables in the same dataset show once,
  // not as five separate lines.
  const byKind = {};
  for (const u of usagesData.used_by) {
    (byKind[u.kind] = byKind[u.kind] || []).push(u);
  }
  const rows = [];
  for (const [k, us] of Object.entries(byKind)) {
    const byObject = {};
    for (const u of us) {
      const key = `${u.key} ${u.label}`;
      (byObject[key] = byObject[key] || { key: u.key, label: u.label, fields: new Set() }).fields.add(u.field);
    }
    for (const obj of Object.values(byObject)) {
      rows.push(
        el("div", { class: "usage-row" }, [
          el("span", { class: "usage-kind" }, kindLabel(k)),
          el("button", { class: "usage-link", type: "button", onclick: () => selectItem(k, obj.key) }, obj.label),
          el("span", { class: "usage-field" }, `via ${[...obj.fields].join(", ")}`),
        ])
      );
    }
  }
  return el("div", { class: "usages-panel" }, [el("div", { class: "usages-title" }, `Used by ${usagesData.used_by.length === 1 ? "1 object" : `${rows.length} object(s)`}:`), ...rows]);
}

// ---------------------------------------------------------------------------
// A minimal modal dialog - this app's first multi-step interaction that doesn't
// fit prompt()/confirm(). `bodyBuilder(close)` builds the modal's content; `close()`
// tears the overlay down (also wired to Escape and clicking outside the modal).
// ---------------------------------------------------------------------------

function openModal(title, bodyBuilder, onClose) {
  const overlay = el("div", { class: "modal-overlay", onclick: (e) => { if (e.target === overlay) close(); } });
  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    overlay.remove();
    document.removeEventListener("keydown", onKeydown);
    if (onClose) onClose();
  }
  function onKeydown(e) {
    if (e.key === "Escape") close();
  }
  document.addEventListener("keydown", onKeydown);
  const modal = el("div", { class: "modal" }, [
    el("div", { class: "modal-header" }, [el("div", { class: "modal-title" }, title), el("button", { class: "modal-close", type: "button", onclick: close }, "✕")]),
    el("div", { class: "modal-body" }, [bodyBuilder(close)]),
  ]);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
  return close;
}

// ---------------------------------------------------------------------------
// "Copy variables from..." - datasets only, next to the variables list's own
// "+ Add variable". Orchestrated server-side (webui/copy_variables.py): one copy can
// touch several files (the target dataset, plus any duplicated methods/comments/
// value lists/where-clauses), which a single POST keeps atomic-ish in a way a
// sequence of separate frontend calls wouldn't be.
// ---------------------------------------------------------------------------

function copyVariablesButton(targetDatasetKey, getExistingVariableNames, onCopied) {
  return el(
    "button",
    {
      class: "secondary",
      type: "button",
      style: "margin-top:8px;margin-left:8px;",
      // Read the current name set fresh on click, not once at render time - the user
      // may have added/removed variables since this button was drawn.
      onclick: () => openCopyVariablesModal(targetDatasetKey, getExistingVariableNames(), onCopied),
    },
    "Copy variables from..."
  );
}

function openCopyVariablesModal(targetDatasetKey, existingVariableNames, onCopied) {
  // openModal hands the real close() to its bodyBuilder callback, but this function
  // builds its body as one long sequence up front rather than as that callback itself
  // (easier to follow than nesting the whole thing) - so `close` starts as a no-op and
  // gets replaced with the real one below, before openModal ever shows the dialog to
  // the user (and therefore before any handler referencing it can possibly fire).
  let close = () => {};
  const otherDatasets = (state.itemsByKind.datasets || []).filter((i) => i.key !== targetDatasetKey);
  const form = { sourceKey: "", referenceMode: "share", setPredecessor: false, selected: new Set() };

  const body = el("div", {});
  const sourceSelect = el("select", {}, [
    el("option", { value: "" }, "Select a dataset…"),
    ...otherDatasets.map((i) => el("option", { value: i.key }, i.label)),
  ]);
  const varListBox = el("div", { style: "margin:10px 0;max-height:260px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;padding:8px 10px;" }, [
    el("div", { class: "field-hint" }, "Pick a source dataset above first."),
  ]);
  const selectAllRow = el("div", { hidden: true, style: "margin-bottom:6px;" }, [
    el("button", { class: "secondary", type: "button", style: "font-size:11px;padding:3px 8px;margin-right:6px;", onclick: () => { form.selected = new Set(currentCopyableNames()); renderVarList(); } }, "Select all"),
    el("button", { class: "secondary", type: "button", style: "font-size:11px;padding:3px 8px;", onclick: () => { form.selected.clear(); renderVarList(); } }, "Select none"),
  ]);
  let currentSourceVariables = [];

  function currentCopyableNames() {
    return currentSourceVariables.filter((v) => !existingVariableNames.has(v.name)).map((v) => v.name);
  }

  function renderVarList() {
    clear(varListBox);
    if (!currentSourceVariables.length) {
      varListBox.appendChild(el("div", { class: "field-hint" }, "This dataset has no variables."));
      return;
    }
    for (const v of currentSourceVariables) {
      const alreadyExists = existingVariableNames.has(v.name);
      const checkbox = el("input", {
        type: "checkbox",
        disabled: alreadyExists ? "" : null,
        onchange: (e) => {
          if (e.target.checked) form.selected.add(v.name);
          else form.selected.delete(v.name);
          updateConfirmState();
        },
      });
      checkbox.checked = form.selected.has(v.name);
      varListBox.appendChild(
        el("label", { style: `display:flex;align-items:baseline;gap:6px;padding:2px 0;font-size:13px;${alreadyExists ? "color:var(--text-dim);" : ""}` }, [
          checkbox,
          v.name,
          v.label ? el("span", { style: "color:var(--text-dim);font-size:11px;" }, `- ${v.label}`) : null,
          alreadyExists ? el("span", { class: "orphan-badge", style: "background:var(--bg-alt);color:var(--text-dim);" }, "already exists") : null,
        ])
      );
    }
  }

  sourceSelect.addEventListener("change", async () => {
    form.sourceKey = sourceSelect.value;
    form.selected.clear();
    predecessorCheckbox.parentElement.querySelector("span") && (predecessorCheckbox.parentElement.querySelector("span").textContent = ` Set origin to Predecessor from ${form.sourceKey || "…"}`);
    if (!form.sourceKey) {
      currentSourceVariables = [];
      selectAllRow.hidden = true;
      renderVarList();
      return;
    }
    clear(varListBox);
    varListBox.appendChild(el("div", { class: "field-hint" }, "Loading…"));
    try {
      const { data } = await API.get("datasets", form.sourceKey);
      currentSourceVariables = data.variables || [];
    } catch (err) {
      currentSourceVariables = [];
      showStatus(false, describeError(err));
    }
    selectAllRow.hidden = currentSourceVariables.length === 0;
    renderVarList();
    updateConfirmState();
  });

  const predecessorCheckbox = el("input", { type: "checkbox", onchange: (e) => (form.setPredecessor = e.target.checked) });

  const confirmBtn = el("button", { class: "primary", type: "button", disabled: "" }, "Copy variables");
  function updateConfirmState() {
    confirmBtn.disabled = form.selected.size === 0;
    confirmBtn.textContent = form.selected.size ? `Copy ${form.selected.size} variable${form.selected.size === 1 ? "" : "s"}` : "Copy variables";
  }

  body.appendChild(fieldRow("Source dataset", sourceSelect));
  body.appendChild(selectAllRow);
  body.appendChild(varListBox);
  body.appendChild(
    el("div", { class: "field-row" }, [
      el("label", {}, "Referenced comments, methods, value lists and where clauses"),
      el("div", { style: "display:flex;flex-direction:column;gap:6px;margin-top:4px;" }, [
        el("label", { style: "display:flex;align-items:center;gap:6px;font-weight:400;font-size:13px;" }, [
          el("input", { type: "radio", name: "ref-mode", checked: "", onchange: () => (form.referenceMode = "share") }),
          "Share - copied variables keep pointing at the source's objects",
        ]),
        el("label", { style: "display:flex;align-items:center;gap:6px;font-weight:400;font-size:13px;" }, [
          el("input", { type: "radio", name: "ref-mode", onchange: () => (form.referenceMode = "duplicate") }),
          "Duplicate - give this dataset its own independent copies",
        ]),
      ]),
      el("div", { class: "field-hint" }, "Codelists are always shared, regardless of this choice - they're controlled terminology, meant to be reused, not owned by one dataset."),
    ])
  );
  body.appendChild(
    el("div", { class: "field-row" }, [
      el("label", { style: "display:flex;align-items:center;gap:6px;font-weight:400;font-size:13px;color:var(--text);" }, [predecessorCheckbox, el("span", {}, " Set origin to Predecessor from …")]),
      el("div", { class: "field-hint" }, "Replaces each copied variable's origin: with {type: Predecessor, source: \"<source dataset>.<variable>\"}, discarding whatever origin it had."),
    ])
  );

  const errorBox = el("div", {});
  body.appendChild(errorBox);
  body.appendChild(
    el("div", { style: "display:flex;justify-content:flex-end;gap:8px;margin-top:16px;" }, [
      el("button", { class: "secondary", type: "button", onclick: () => close() }, "Cancel"),
      confirmBtn,
    ])
  );

  confirmBtn.addEventListener("click", async () => {
    confirmBtn.disabled = true;
    clear(errorBox);
    try {
      const result = await apiSend("POST", `/api/kinds/datasets/items/${encodeKey(targetDatasetKey)}/copy-variables`, {
        source_key: form.sourceKey,
        variable_names: [...form.selected],
        reference_mode: form.referenceMode,
        set_predecessor: form.setPredecessor,
      });
      close();
      const parts = [`Copied ${result.copied.length} variable${result.copied.length === 1 ? "" : "s"}.`];
      if (result.skipped.length) parts.push(`Skipped: ${result.skipped.map((s) => `${s.name} (${s.reason})`).join(", ")}.`);
      if (result.created.length) parts.push(`Created ${result.created.length} new file${result.created.length === 1 ? "" : "s"}.`);
      showStatus(true, parts.join(" "));
      onCopied();
    } catch (err) {
      errorBox.innerHTML = "";
      errorBox.appendChild(el("div", { class: "error-list" }, [el("div", {}, describeError(err))]));
      confirmBtn.disabled = false;
    }
  });

  return openModal("Copy variables from another dataset", (c) => {
    close = c;
    return body;
  });
}

function rawJsonEditor(working, onParsed) {
  const ta = el("textarea", { class: "code", style: "min-height:400px;", oninput: (e) => { ta.dataset.text = e.target.value; notifyDirty(); } });
  ta.value = JSON.stringify(working, null, 2);
  ta.dataset.text = ta.value;
  ta.parse = () => {
    try {
      return JSON.parse(ta.dataset.text);
    } catch (err) {
      throw new Error(`invalid JSON: ${err.message}`);
    }
  };
  return ta;
}

function renderEmptyState(text) {
  const editorEl = document.getElementById("editor");
  if (!editorEl) return; // setup screen replaced the two-pane layout
  clear(editorEl);
  editorEl.appendChild(el("div", { id: "empty-state" }, text || "Pick an object on the left to edit it."));
}

// `define` with no arguments starts the server with no tree (server.py's /api/setup/*).
// Replace the two-pane layout with a launcher: reopen a recent tree, browse to one, or
// scaffold a new one - then reload once the server has adopted the choice.
async function renderSetup() {
  document.title = "Open a define tree - define edit";
  const appEl = document.getElementById("app");
  clear(appEl);

  // If a tree is already open (this is "Open another tree", not first-run), offer a
  // way back to it - reloading returns here since the server's root is unchanged.
  let currentSource = null;
  try {
    currentSource = (await API.info()).source;
  } catch {
    /* first run - no tree open */
  }

  const errLine = el("div", { class: "setup-error", hidden: true });

  function fail(err) {
    const msg = describeError(err);
    errLine.textContent = msg;
    errLine.hidden = false;
    showStatus(false, msg);
  }
  function fieldRow(label, input) {
    return el("div", { class: "field-row" }, [el("label", {}, label), input]);
  }
  async function adopt(promise, btn) {
    errLine.hidden = true;
    if (btn) btn.disabled = true;
    try {
      await promise;
      location.reload();
    } catch (err) {
      if (btn) btn.disabled = false;
      fail(err);
    }
  }

  // --- recently opened trees (server already dropped any that moved/vanished) ---
  let recent = [];
  try {
    recent = (await API.setupRecent()).recent || [];
  } catch {
    /* no recents endpoint / none recorded */
  }
  const recentBox = el("div", { class: "setup-recent" });
  if (recent.length) {
    recentBox.appendChild(el("div", { class: "setup-section-title" }, "Recent"));
    for (const r of recent) {
      recentBox.appendChild(el("button", { class: "setup-recent-row", type: "button", title: r.path, onclick: (e) => adopt(API.setupOpen(r.path), e.currentTarget) }, [
        el("div", { class: "setup-recent-head" }, [
          el("span", { class: "setup-recent-name" }, r.name),
          r.protocol ? el("span", { class: "setup-recent-proto" }, r.protocol) : null,
        ]),
        el("div", { class: "setup-recent-path" }, r.path),
      ]));
    }
  }

  // --- browse + create (one folder context drives both) ---
  const pathLine = el("div", { class: "setup-path" });
  const listBox = el("div", { class: "setup-list" });
  const openRow = el("div", { class: "setup-actions" });
  const cFolder = el("input", { type: "text", value: "define" });
  const cStudy = el("input", { type: "text", placeholder: "e.g. ABC-101" });
  const cProto = el("input", { type: "text", placeholder: "defaults to the study name" });
  const cHint = el("div", { class: "setup-note" });
  const cBtn = el("button", { class: "primary", type: "button" }, "Create & open");
  let folderPath = null;

  async function go(path) {
    errLine.hidden = true;
    try {
      renderBrowser(await API.setupBrowse(path));
    } catch (err) {
      fail(err);
    }
  }

  function renderBrowser(data) {
    folderPath = data.path;
    clear(pathLine);
    pathLine.appendChild(el("span", { class: "setup-path-label" }, "Location"));
    pathLine.appendChild(el("code", {}, data.path));
    if (!data.writable) pathLine.appendChild(el("span", { class: "setup-tag warn" }, "read-only"));

    clear(listBox);
    if (data.parent) {
      listBox.appendChild(el("button", { class: "setup-row up", type: "button", onclick: () => go(data.parent) }, "↑  parent folder"));
    }
    for (const e of data.entries) {
      listBox.appendChild(el("button", { class: "setup-row", type: "button", onclick: () => go(e.path) }, [
        el("span", { class: "setup-row-name" }, e.name),
        e.is_tree ? el("span", { class: "setup-tag" }, "define tree") : null,
      ]));
    }
    if (!data.entries.length) {
      listBox.appendChild(el("div", { class: "setup-note" }, "no sub-folders here"));
    }

    clear(openRow);
    if (data.is_tree) {
      openRow.appendChild(el("button", { class: "primary", type: "button", onclick: (e) => adopt(API.setupOpen(data.path), e.currentTarget) }, "Open this folder"));
    } else {
      openRow.appendChild(el("div", { class: "setup-note" }, "open a folder that contains study.yaml, or create one below"));
    }
    cHint.textContent = `A new folder is created inside ${data.path}`;
    cBtn.disabled = !data.writable;
  }

  cBtn.onclick = (e) => {
    if (!cStudy.value.trim()) {
      cStudy.focus();
      return;
    }
    adopt(
      API.setupInit({
        parent: folderPath,
        name: cFolder.value.trim() || "define",
        study_name: cStudy.value.trim(),
        protocol_name: cProto.value.trim(),
      }),
      e.currentTarget,
    );
  };

  const folderPanel = el("details", { class: "setup-folder", open: recent.length ? null : "" }, [
    el("summary", {}, recent.length ? "Open another folder, or create a new tree" : "Choose a folder"),
    el("div", { class: "setup-browser" }, [pathLine, listBox]),
    openRow,
    el("div", { class: "setup-divider" }, "or create a new tree"),
    el("div", { class: "setup-create" }, [
      fieldRow("New folder name", cFolder),
      fieldRow("Study name", cStudy),
      fieldRow("Protocol name", cProto),
      cHint,
      cBtn,
    ]),
  ]);

  appEl.appendChild(el("div", { class: "setup-wrap" }, [
    currentSource
      ? el("button", { class: "setup-back", type: "button", onclick: () => location.reload() }, "← Back to the current tree")
      : null,
    el("h1", { class: "setup-title" }, "Open a define tree"),
    el("p", { class: "setup-intro" }, recent.length
      ? "Reopen one you've worked on, browse to another folder, or start a new tree."
      : "Choose a folder for your define YAML files - browse to a tree you already have, or create a new one."),
    errLine,
    recentBox,
    folderPanel,
  ]));

  await go(null);
}

function renderEditor() {
  const editorEl = document.getElementById("editor");
  clear(editorEl);
  const { kind, key } = state.selection;
  const isNew = state.isNew;

  const header = el("div", { class: "editor-header" }, [
    el("div", {}, [el("div", { class: "editor-title" }, isNew ? `New ${kind} - ${key}` : key), el("div", { class: "editor-subtitle" }, `${kind}/${key}.yaml`)]),
  ]);

  const actions = el("div", { class: "editor-actions" });
  actions.appendChild(el("span", { id: "dirty-indicator", style: "font-size:12px;color:var(--text-dim);align-self:center;margin-right:4px;" }, ""));
  const autosaveToggle = el("input", {
    type: "checkbox",
    onchange: (e) => {
      state.autosave = e.target.checked;
      API.putEditorState({ autosave: state.autosave }).catch(() => {});
      if (state.autosave && state.dirty) currentSave();
    },
  });
  autosaveToggle.checked = state.autosave;
  actions.appendChild(
    el("label", { style: "display:flex;align-items:center;gap:5px;font-size:12px;color:var(--text-dim);align-self:center;margin-right:4px;cursor:pointer;" }, [autosaveToggle, "Autosave"])
  );
  const rawBtn = el("button", { class: "secondary", type: "button", onclick: () => { state.raw = !state.raw; renderEditor(); } }, state.raw ? "Structured" : "Raw JSON");
  actions.appendChild(rawBtn);
  if (!SINGLETON_KINDS[kind]) {
    actions.appendChild(
      el(
        "button",
        {
          class: "danger",
          type: "button",
          onclick: async () => {
            if (!confirm(`Delete ${kind}/${key}.yaml?`)) return;
            try {
              await API.remove(kind, key);
              delete state.itemsByKind[kind];
              state.selection = null;
              await loadKindItems(kind);
              renderSidebar();
              renderEmptyState("Deleted. Pick another object on the left.");
            } catch (err) {
              showStatus(false, describeError(err));
            }
          },
        },
        "Delete"
      )
    );
  }
  const saveBtn = el("button", { class: "primary", type: "button", onclick: () => doSave() }, "Save");
  actions.appendChild(saveBtn);
  header.appendChild(actions);
  editorEl.appendChild(header);

  if (!isNew && !SINGLETON_KINDS[kind]) {
    editorEl.appendChild(renderUsagesPanel(state.usages));
  }

  const errorBox = el("div", { id: "error-box" });
  editorEl.appendChild(errorBox);

  const body = el("div", { id: "editor-body" });
  editorEl.appendChild(body);

  let rawTa = null;
  if (state.raw) {
    rawTa = rawJsonEditor(state.working);
    body.appendChild(rawTa);
  } else {
    const builder = EDITORS[kind];
    if (builder) {
      body.appendChild(builder(state.working));
    } else {
      body.appendChild(el("div", { class: "field-hint" }, "No structured editor for this kind yet - use Raw JSON."));
    }
  }

  async function doSave() {
    let payload = state.working;
    if (state.raw) {
      try {
        payload = rawTa.parse();
        state.working = payload;
      } catch (err) {
        showStatus(false, err.message);
        return;
      }
    }
    saveBtn.disabled = true;
    clear(errorBox);
    try {
      await API.save(kind, key, payload);
      showStatus(true, "Saved.");
      state.isNew = false;
      state.dirty = false;
      updateDirtyIndicator();
      await loadKindItems(kind);
      renderSidebar();
    } catch (err) {
      renderErrors(errorBox, err);
      showStatus(false, "Not saved - see errors above.");
    } finally {
      saveBtn.disabled = false;
    }
  }

  currentSave = doSave;
}

function renderErrors(box, err) {
  clear(box);
  const detail = err.body && err.body.detail;
  if (!detail) {
    box.appendChild(el("div", { class: "error-list" }, [el("div", {}, describeError(err))]));
    return;
  }
  const items = Array.isArray(detail) ? detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`) : [String(detail)];
  box.appendChild(el("div", { class: "error-list" }, items.map((t) => el("div", {}, t))));
}

function describeError(err) {
  if (err && err.body && err.body.detail) return typeof err.body.detail === "string" ? err.body.detail : JSON.stringify(err.body.detail);
  return err && err.message ? err.message : String(err);
}

let statusTimer = null;
function showStatus(ok, text) {
  let bar = document.getElementById("status-bar");
  if (!bar) {
    bar = el("div", { id: "status-bar", class: "status-bar" });
    document.body.appendChild(bar);
  }
  bar.className = `status-bar ${ok ? "ok" : "error"}`;
  bar.textContent = text;
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => (bar.className = "status-bar"), 4000);
}

// ---------------------------------------------------------------------------
// Sidebar / navigation
// ---------------------------------------------------------------------------

async function loadKindItems(kind) {
  state.itemsByKind[kind] = await API.items(kind);
}

// Which top-level sidebar kind-groups are collapsed. In-memory only (unlike the
// server-persisted last-view/autosave state) - resets on reload, same as any
// ordinary tree-view expand state.
const sidebarCollapsed = new Set();

function renderSidebar() {
  const tree = document.getElementById("sidebar-tree");
  clear(tree);
  tree.appendChild(
    el("div", { class: "sidebar-toolbar" }, [
      el(
        "button",
        {
          class: "secondary",
          type: "button",
          style: "font-size:11px;padding:3px 8px;margin-right:6px;",
          onclick: () => { sidebarCollapsed.clear(); renderSidebar(); },
        },
        "Expand all"
      ),
      el(
        "button",
        {
          class: "secondary",
          type: "button",
          style: "font-size:11px;padding:3px 8px;",
          onclick: () => { for (const meta of state.kinds) sidebarCollapsed.add(meta.kind); renderSidebar(); },
        },
        "Collapse all"
      ),
    ])
  );
  for (const meta of state.kinds) {
    const items = state.itemsByKind[meta.kind] || [];
    // Never render a group collapsed if it contains the current selection - the
    // selected item should always stay visible in the sidebar.
    const containsSelection = state.selection && state.selection.kind === meta.kind;
    const collapsed = sidebarCollapsed.has(meta.kind) && !containsSelection;

    const group = el("div", { class: "kind-group" });
    const itemsBox = el("div", { class: "kind-items", hidden: collapsed || null });
    const chevron = el("span", { style: "display:inline-block;width:12px;" }, collapsed ? "▸" : "▾");
    const header = el(
      "div",
      {
        class: "kind-group-header",
        onclick: () => {
          if (sidebarCollapsed.has(meta.kind)) sidebarCollapsed.delete(meta.kind);
          else sidebarCollapsed.add(meta.kind);
          renderSidebar();
        },
      },
      [
        el("span", {}, [chevron, meta.label]),
        meta.singleton ? null : el("button", { class: "kind-add", type: "button", title: `New ${meta.label}`, onclick: (e) => { e.stopPropagation(); newItem(meta.kind); } }, "+"),
      ]
    );
    group.appendChild(header);
    if (items.length === 0) {
      itemsBox.appendChild(el("div", { class: "kind-empty" }, meta.singleton ? "not created yet" : "none"));
      if (meta.singleton) {
        itemsBox.appendChild(el("button", { class: "row-add", type: "button", onclick: () => newItem(meta.kind) }, `+ Create ${meta.label.toLowerCase()}.yaml`));
      }
    }
    // Datasets are the one kind whose sequence is real content - the ItemGroupDef
    // order define.html is read top-to-bottom in (CLAUDE.md's study.yaml
    // dataset_order:) - so they're the only kind that gets reorder controls here.
    // Every other kind's document order is cosmetic (each object is independently
    // OID-referenced), so reordering there would just be UI for its own sake.
    const reorderable = meta.kind === "datasets";
    function moveDatasetItem(fromIdx, toIdx) {
      if (fromIdx === toIdx || fromIdx < 0 || fromIdx >= items.length || toIdx < 0 || toIdx >= items.length) return;
      const [moved] = items.splice(fromIdx, 1);
      items.splice(toIdx, 0, moved);
      API.putDatasetOrder(items.map((i) => i.name).filter(Boolean)).catch(() => {});
      renderSidebar();
    }
    let dragFromIdx = null;
    items.forEach((item, idx) => {
      const selected = state.selection && state.selection.kind === meta.kind && state.selection.key === item.key;
      const label = item.orphan ? [item.label, el("span", { class: "orphan-badge", title: "Nothing else references this" }, "unused")] : item.label;
      const button = el("button", { class: `kind-item${selected ? " selected" : ""}`, type: "button", onclick: () => selectItem(meta.kind, item.key) }, label);
      if (!reorderable) {
        itemsBox.appendChild(button);
        return;
      }
      const row = el("div", {
        class: "kind-item-row",
        ondragover: (e) => { e.preventDefault(); row.classList.add("drag-over"); },
        ondragleave: () => row.classList.remove("drag-over"),
        ondrop: (e) => {
          e.preventDefault();
          row.classList.remove("drag-over");
          if (dragFromIdx !== null) moveDatasetItem(dragFromIdx, idx);
          dragFromIdx = null;
        },
      });
      row.appendChild(el("span", { class: "drag-handle", draggable: "true", title: "Drag to reorder", ondragstart: (e) => { dragFromIdx = idx; e.dataTransfer.effectAllowed = "move"; }, ondragend: () => (dragFromIdx = null) }, "⠿"));
      row.appendChild(button);
      row.appendChild(
        el("span", { class: "kind-item-move" }, [
          el("button", { class: "row-move", type: "button", title: "Move up", disabled: idx === 0 ? "" : null, onclick: () => moveDatasetItem(idx, idx - 1) }, "▲"),
          el("button", { class: "row-move", type: "button", title: "Move down", disabled: idx === items.length - 1 ? "" : null, onclick: () => moveDatasetItem(idx, idx + 1) }, "▼"),
        ])
      );
      itemsBox.appendChild(row);
    });
    group.appendChild(itemsBox);
    tree.appendChild(group);
  }
}

// Cancel any pending autosave debounced against the *previous* selection - otherwise
// switching objects mid-debounce would save the new working copy under the old key,
// or vice versa.
function resetEditingState() {
  clearTimeout(autosaveTimer);
  state.dirty = false;
  updateDirtyIndicator();
}

async function selectItem(kind, key) {
  const editorEl = document.getElementById("editor");
  clear(editorEl);
  editorEl.appendChild(loadingBlock(`Loading ${key}…`));
  try {
    const { data, usages } = await API.get(kind, key);
    resetEditingState();
    state.selection = { kind, key };
    state.working = data;
    state.usages = usages || null;
    state.isNew = false;
    state.raw = false;
    renderSidebar();
    renderEditor();
    API.putEditorState({ kind, key }).catch(() => {});
  } catch (err) {
    showStatus(false, describeError(err));
    // Put the pane back the way it was - the previous object, or the empty state.
    if (state.selection) renderEditor();
    else renderEmptyState();
  }
}

const NEW_ITEM_SKELETONS = {
  study: { odm: { file_oid: "" }, study: { oid: "", name: "", protocol_name: "" }, metadata_version: { oid: "", name: "" } },
  standards: { standards: [] },
  documents: { documents: [] },
  datasets: { name: "", label: "", class: "", structure: "", variables: [] },
  codelists: { name: "", label: "", type: "text", terms: [] },
  methods: { name: "", type: "Computation" },
  comments: { description: "" },
  whereclauses: { conditions: [] },
  valuelists: { dataset: "", variable: "", entries: [] },
  analysis_results: { name: "", title: "", document: { ref: "" }, results: [] },
};

function newItem(kind) {
  if (kind === "datasets") return openNewDatasetDialog();
  if (kind === "codelists") return openNewCodelistDialog();
  newBlankItem(kind);
}

function newBlankItem(kind, presetKey, presetPatch) {
  let key = presetKey || kind;
  if (!SINGLETON_KINDS[kind] && !presetKey) {
    key = prompt(`File name for the new ${kind} entry (no .yaml, "/" for a subdirectory):`);
    if (!key) return;
  }
  resetEditingState();
  state.selection = { kind, key };
  state.working = JSON.parse(JSON.stringify(NEW_ITEM_SKELETONS[kind] || {}));
  if (presetPatch) Object.assign(state.working, presetPatch);
  state.usages = null; // nothing can reference an object that doesn't exist on disk yet
  state.isNew = true;
  state.raw = false;
  renderSidebar();
  renderEditor();
}

// A standards.yaml entry with standards_file: set (CLAUDE.md §9.2) can scaffold a whole
// dataset (all standard variables of a domain / ADaM structure) or codelists straight
// from the CDISC CSV export. Both dialogs fall back to the plain blank-object path.

async function scaffoldStandardsByKind(fileKind) {
  try {
    return (await apiGet("/api/standards/scaffold/standards")).filter((s) => s.kind === fileKind);
  } catch {
    return [];
  }
}

function openNewDatasetDialog() {
  let close = () => {};
  const body = el("div", {});
  body.appendChild(
    el("div", { style: "margin-bottom:14px;" }, [
      el("button", { class: "secondary", type: "button", onclick: () => { close(); newBlankItem("datasets"); } }, "Blank dataset"),
    ])
  );
  const section = el("div", {});
  body.appendChild(el("div", { class: "field-hint", style: "margin-bottom:6px;" }, "…or scaffold from a standard:"));
  body.appendChild(section);

  scaffoldStandardsByKind("ig").then((standards) => {
    clear(section);
    if (!standards.length) {
      section.appendChild(el("div", { class: "field-hint" }, "No standard has an IG CSV attached. Add one in Standards → Local CSV."));
      return;
    }
    const stdSelect = el("select", {}, [el("option", { value: "" }, "Select a standard…"), ...standards.map((s) => el("option", { value: s.name }, `${s.name} (${s.file})`))]);
    const unitSelect = el("select", { disabled: "" }, [el("option", { value: "" }, "…")]);
    const nameInput = el("input", { type: "text", placeholder: "Dataset name, e.g. AE or ADAE" });
    const keyInput = el("input", { type: "text", placeholder: "File name (optional - defaults from the name)" });
    const errorBox = el("div", {});
    const createBtn = el("button", { class: "primary", type: "button", disabled: "" }, "Create dataset");

    function refreshCreate() {
      createBtn.disabled = !(stdSelect.value && unitSelect.value && nameInput.value.trim());
    }
    stdSelect.onchange = async () => {
      unitSelect.innerHTML = "";
      unitSelect.appendChild(el("option", { value: "" }, "Loading…"));
      unitSelect.disabled = true;
      refreshCreate();
      if (!stdSelect.value) return;
      try {
        const { units } = await apiGet(`/api/standards/scaffold/units?standard=${encodeURIComponent(stdSelect.value)}`);
        unitSelect.innerHTML = "";
        unitSelect.appendChild(el("option", { value: "" }, "Select a dataset / structure…"));
        for (const u of units) unitSelect.appendChild(el("option", { value: u.unit }, `${u.unit} - ${u.variable_count} variables`));
        unitSelect.disabled = false;
      } catch (err) {
        unitSelect.innerHTML = "";
        unitSelect.appendChild(el("option", { value: "" }, "-"));
        errorBox.textContent = describeError(err);
      }
      refreshCreate();
    };
    unitSelect.onchange = () => { if (unitSelect.value && !nameInput.value.trim() && !/\s/.test(unitSelect.value)) nameInput.value = unitSelect.value; refreshCreate(); };
    nameInput.oninput = refreshCreate;
    createBtn.onclick = async () => {
      createBtn.disabled = true;
      clear(errorBox);
      try {
        const res = await apiSend("POST", "/api/standards/scaffold/dataset", {
          standard: stdSelect.value, unit: unitSelect.value, name: nameInput.value.trim(), key: keyInput.value.trim() || null,
        });
        close();
        await loadKindItems("datasets");
        renderSidebar();
        showStatus(true, `Created dataset ${res.key} with ${res.variable_count} variables - fill in label/structure, then review types.`);
        selectItem("datasets", res.key);
      } catch (err) {
        errorBox.appendChild(el("div", { class: "error-list" }, [el("div", {}, describeError(err))]));
        createBtn.disabled = false;
      }
    };

    section.appendChild(fieldRow("Standard", stdSelect));
    section.appendChild(fieldRow("Dataset / structure", unitSelect));
    section.appendChild(fieldRow("Dataset name", nameInput));
    section.appendChild(fieldRow("File name", keyInput));
    section.appendChild(errorBox);
    section.appendChild(el("div", { style: "display:flex;justify-content:flex-end;margin-top:12px;" }, [createBtn]));
  });

  close = openModal("New dataset", () => body);
}

// Start a blank codelist file, optionally pre-naming it (and deriving its file key from
// that name) - used both by the "Blank codelist" button and by the codelist picker's
// "create this name" path.
function startNewBlankCodelist(name) {
  if (state.dirty && !confirm("You have unsaved changes that will be lost. Continue to the new codelist?")) return;
  const clean = (name || "").trim();
  const slug = clean.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  newBlankItem("codelists", slug || undefined, clean ? { name: clean } : undefined);
}

function openNewCodelistDialog(presetName) {
  let close = () => {};
  const body = el("div", {});
  body.appendChild(
    el("div", { style: "margin-bottom:14px;" }, [
      el("button", { class: "secondary", type: "button", onclick: () => { close(); startNewBlankCodelist(presetName); } }, "Blank codelist"),
    ])
  );

  const missingBox = el("div", { style: "margin-bottom:14px;" });
  body.appendChild(missingBox);
  apiGet("/api/standards/scaffold/missing-codelists").then((res) => {
    const resolvable = res.missing.filter((m) => m.standard);
    if (!resolvable.length) return;
    const btn = el("button", { class: "primary", type: "button" }, `Add ${resolvable.length} referenced-but-missing codelist${resolvable.length === 1 ? "" : "s"}`);
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        const r = await apiSend("POST", "/api/standards/scaffold/missing-codelists", {});
        close();
        await loadKindItems("codelists");
        renderSidebar();
        showStatus(true, `Created ${r.created.length} codelist${r.created.length === 1 ? "" : "s"}.`);
      } catch (err) {
        showStatus(false, describeError(err));
        btn.disabled = false;
      }
    };
    missingBox.appendChild(btn);
    const unresolved = res.missing.filter((m) => !m.standard).map((m) => m.ref);
    if (unresolved.length) missingBox.appendChild(el("div", { class: "field-hint" }, `Not in any attached CT file: ${unresolved.join(", ")}`));
  }).catch(() => {});

  const section = el("div", {});
  body.appendChild(el("div", { class: "field-hint", style: "margin-bottom:6px;" }, "…or pick from a standard's CT:"));
  body.appendChild(section);

  scaffoldStandardsByKind("ct").then((standards) => {
    clear(section);
    if (!standards.length) {
      section.appendChild(el("div", { class: "field-hint" }, "No standard has a CT CSV attached. Add one in Standards → Local CSV."));
      return;
    }
    const stdSelect = el("select", {}, [el("option", { value: "" }, "Select a CT standard…"), ...standards.map((s) => el("option", { value: s.name }, s.name))]);
    const searchInput = el("input", { type: "text", placeholder: "Filter codelists by submission value or name…" });
    if (presetName) searchInput.value = presetName;
    const listBox = el("div", { style: "margin:8px 0;max-height:200px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;padding:8px 10px;" });
    const configBox = el("div", { style: "margin:8px 0;" });
    const createBtn = el("button", { class: "primary", type: "button", disabled: "" }, "Create codelists");
    const errorBox = el("div", {});
    // value -> { label, term_count, extensible, name, codes: Set|null (null = all), terms: [] | null }
    const selected = new Map();

    function refresh() {
      createBtn.disabled = selected.size === 0;
      createBtn.textContent = selected.size ? `Create ${selected.size} codelist${selected.size === 1 ? "" : "s"}` : "Create codelists";
    }

    function renderConfig() {
      clear(configBox);
      if (!selected.size) return;
      configBox.appendChild(el("div", { class: "field-hint", style: "margin-bottom:4px;" }, "Rename each codelist and/or keep only a subset of its terms (a subset is a sponsor codelist - tick “Non-standard” on it afterwards if your validator needs it):"));
      for (const [value, e] of selected) {
        const card = el("div", { class: "expr-block", style: "padding:8px 10px;" });
        card.appendChild(el("div", { class: "expr-block-header" }, [
          el("b", {}, value),
          el("button", { class: "row-remove", type: "button", onclick: () => { selected.delete(value); loadList(); renderConfig(); refresh(); } }, "✕"),
        ]));
        const nameInput = el("input", { type: "text", value: e.name, oninput: (ev) => (e.name = ev.target.value) });
        card.appendChild(fieldRow("Name", nameInput));

        const termsHost = el("div", {});
        card.appendChild(termsHost);
        const renderTerms = () => {
          clear(termsHost);
          if (e.terms === null) { termsHost.appendChild(el("div", { class: "field-hint" }, "Loading terms…")); return; }
          const total = e.terms.length;
          const kept = e.codes ? e.codes.size : total;
          termsHost.appendChild(el("div", { style: "display:flex;gap:8px;align-items:baseline;margin:4px 0;" }, [
            el("span", { class: "field-hint" }, `${kept} of ${total} terms`),
            el("button", { class: "secondary", type: "button", style: "font-size:11px;padding:2px 6px;", onclick: () => { e.codes = null; renderTerms(); } }, "All"),
            el("button", { class: "secondary", type: "button", style: "font-size:11px;padding:2px 6px;", onclick: () => { e.codes = new Set(); renderTerms(); } }, "None"),
          ]));
          const grid = el("div", { style: "max-height:150px;overflow-y:auto;border:1px solid var(--border);border-radius:4px;padding:6px 8px;" });
          for (const t of e.terms) {
            const on = !e.codes || e.codes.has(t.code);
            const cb = el("input", { type: "checkbox", onchange: (ev) => {
              if (!e.codes) e.codes = new Set(e.terms.map((x) => x.code));
              ev.target.checked ? e.codes.add(t.code) : e.codes.delete(t.code);
              if (e.codes.size === e.terms.length) e.codes = null;
              renderTerms();
            } });
            cb.checked = on;
            grid.appendChild(el("label", { style: "display:flex;gap:6px;font-size:12px;padding:1px 0;" }, [
              cb, el("span", { style: "font-family:var(--mono);" }, t.code),
              t.decode ? el("span", { style: "color:var(--text-dim);" }, `- ${t.decode}`) : null,
            ]));
          }
          termsHost.appendChild(grid);
        };
        renderTerms();
        if (e.terms === null) {
          apiGet(`/api/standards/scaffold/ct-codelist-terms?standard=${encodeURIComponent(stdSelect.value)}&value=${encodeURIComponent(value)}`)
            .then((d) => { e.terms = d.terms || []; renderTerms(); })
            .catch((err) => { e.terms = []; termsHost.textContent = describeError(err); });
        }
        configBox.appendChild(card);
      }
    }

    async function loadList() {
      clear(listBox);
      if (!stdSelect.value) { listBox.appendChild(el("div", { class: "field-hint" }, "Pick a CT standard first.")); return; }
      listBox.appendChild(el("div", { class: "field-hint" }, "Loading…"));
      try {
        const { codelists } = await apiGet(`/api/standards/scaffold/ct-codelists?standard=${encodeURIComponent(stdSelect.value)}&q=${encodeURIComponent(searchInput.value.trim())}`);
        clear(listBox);
        if (!codelists.length) { listBox.appendChild(el("div", { class: "field-hint" }, "No matches - keep typing to narrow it down.")); return; }
        for (const c of codelists) {
          const cb = el("input", { type: "checkbox", onchange: (ev) => {
            if (ev.target.checked) selected.set(c.value, { label: c.label, term_count: c.term_count, extensible: c.extensible, name: c.value, codes: null, terms: null });
            else selected.delete(c.value);
            renderConfig(); refresh();
          } });
          cb.checked = selected.has(c.value);
          listBox.appendChild(el("label", { style: "display:flex;align-items:baseline;gap:6px;padding:2px 0;font-size:13px;" }, [
            cb, el("b", {}, c.value),
            el("span", { style: "color:var(--text-dim);font-size:11px;" }, `- ${c.label} (${c.term_count} terms${c.extensible ? ", extensible" : ""})`),
          ]));
        }
      } catch (err) {
        clear(listBox);
        listBox.appendChild(el("div", { class: "error-list" }, [el("div", {}, describeError(err))]));
      }
    }
    stdSelect.onchange = () => { selected.clear(); renderConfig(); refresh(); loadList(); };
    let deb;
    searchInput.oninput = () => { clearTimeout(deb); deb = setTimeout(loadList, 250); };
    createBtn.onclick = async () => {
      createBtn.disabled = true;
      clear(errorBox);
      const items = [...selected].map(([value, e]) => {
        const it = { value, name: (e.name || "").trim() || value };
        if (e.codes) it.codes = [...e.codes];
        return it;
      });
      try {
        const r = await apiSend("POST", "/api/standards/scaffold/codelists", { standard: stdSelect.value, items });
        close();
        await loadKindItems("codelists");
        renderSidebar();
        const parts = [`Created ${r.created.length} codelist${r.created.length === 1 ? "" : "s"}.`];
        if (r.skipped.length) parts.push(`Skipped: ${r.skipped.map((s) => `${s.value} (${s.reason})`).join(", ")}.`);
        showStatus(true, parts.join(" "));
      } catch (err) {
        errorBox.appendChild(el("div", { class: "error-list" }, [el("div", {}, describeError(err))]));
        createBtn.disabled = false;
      }
    };

    section.appendChild(fieldRow("CT standard", stdSelect));
    section.appendChild(searchInput);
    section.appendChild(listBox);
    section.appendChild(configBox);
    section.appendChild(errorBox);
    section.appendChild(el("div", { style: "display:flex;justify-content:flex-end;margin-top:8px;" }, [createBtn]));
  });

  close = openModal("New codelist", () => body);
}

// Double-clicking a variable's Codelist / Method / Comment field opens this generic
// picker: a search box (pre-filled with whatever's already typed) over every object of
// that kind in the tree, matched case-insensitively; an empty box lists them all.
// Picking one writes its reference value into the field. If the box holds a value that
// no object has, an "add it" action confirms and then opens that kind's create flow
// pre-named - so a variable can point at an object that doesn't exist yet and be
// followed straight into creating it.
//
// Matching is two-tier: name/label/file-key matches show first (bold, from the
// already-loaded sidebar list, so they're instant); then a debounced call to
// /api/kinds/{kind}/search adds objects the query only turned up *inside* the file
// (searching "male" finds the SEX codelist via its term) - those render italic with a
// snippet of the field that matched.
//
// `cfg`: {
//   kind, title, findLabel, placeholder, emptyText,
//   refValue(item) -> the string written into the field (a codelist's name; a
//     method/comment file key, since those resolve by path),
//   matchText(item) -> the haystack the query is tested against for the instant tier,
//   createLabel(raw), createConfirm  -> the "not found, create it" affordance,
//   onCreate(raw)  -> opens the create flow,
// }
function openRefPicker(cfg, currentText, setValue) {
  let close = () => {};
  const all = state.itemsByKind[cfg.kind] || [];
  let contentHits = []; // [{key, name, label, snippet}] from the last server search
  let contentHitsFor = null; // the query string contentHits belongs to

  const search = el("input", { type: "text", placeholder: cfg.placeholder });
  search.value = (currentText || "").trim();
  const listBox = el("div", { style: "margin:8px 0;max-height:300px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;" });
  const footer = el("div", { style: "margin-top:8px;" });

  const exactMatch = (raw) => {
    const lc = raw.trim().toLowerCase();
    return all.find((i) => cfg.refValue(i).toLowerCase() === lc);
  };

  function row(val, label, { italic, snippet } = {}) {
    return el(
      "button",
      {
        type: "button",
        style: `display:block;width:100%;text-align:left;border:none;background:none;padding:6px 10px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border);${italic ? "font-style:italic;" : ""}`,
        onclick: () => { setValue(val); close(); },
      },
      [
        el("b", { style: italic ? "font-weight:600;" : "" }, val),
        label && label !== val ? el("span", { style: "color:var(--text-dim);font-style:normal;" }, `  -  ${label}`) : null,
        snippet ? el("div", { class: "field-hint", style: "font-style:normal;margin-top:1px;" }, `matched: ${snippet}`) : null,
      ]
    );
  }

  function render() {
    const raw = search.value.trim();
    const q = raw.toLowerCase();
    clear(listBox);
    const nameMatches = q ? all.filter((i) => cfg.matchText(i).toLowerCase().includes(q)) : all.slice();
    const nameKeys = new Set(nameMatches.map((i) => i.key));
    const extras = contentHitsFor === raw ? contentHits.filter((h) => !nameKeys.has(h.key)) : [];

    if (!nameMatches.length && !extras.length) {
      listBox.appendChild(el("div", { class: "field-hint", style: "padding:10px;" }, all.length ? "No matches." : cfg.emptyText));
    }
    for (const i of nameMatches) listBox.appendChild(row(cfg.refValue(i), i.label));
    for (const h of extras) listBox.appendChild(row(cfg.refValue(h), h.label, { italic: true, snippet: h.snippet }));

    clear(footer);
    if (raw && !exactMatch(raw)) {
      footer.appendChild(
        el(
          "button",
          {
            class: "primary",
            type: "button",
            onclick: () => {
              close();
              if (confirm(`"${raw}" ${cfg.createConfirm}`)) {
                setValue(raw);
                cfg.onCreate(raw);
              }
            },
          },
          cfg.createLabel(raw)
        )
      );
    }
  }

  let deb = null;
  function scheduleContentSearch() {
    clearTimeout(deb);
    const raw = search.value.trim();
    if (!raw || raw === contentHitsFor) return;
    deb = setTimeout(async () => {
      try {
        const hits = await apiGet(`/api/kinds/${cfg.kind}/search?q=${encodeURIComponent(raw)}`);
        contentHits = hits.filter((h) => h.match === "content");
        contentHitsFor = raw;
        if (search.value.trim() === raw) render();
      } catch {
        /* keep the instant name-match list */
      }
    }, 220);
  }

  search.addEventListener("input", () => { render(); scheduleContentSearch(); });
  const body = el("div", {}, [fieldRow(cfg.findLabel, search), listBox, footer]);
  render();
  scheduleContentSearch();
  close = openModal(cfg.title, () => body);
  setTimeout(() => search.focus(), 0);
}

// Start a blank one-file-per-object entry (method/comment), keyed by the path the user
// typed in the picker (which is exactly how the reference resolves - CLAUDE.md §3).
function startNewBlankRef(kind, key) {
  if (state.dirty && !confirm(`You have unsaved changes that will be lost. Continue to the new ${kind.replace(/s$/, "")}?`)) return;
  const clean = (key || "").trim().replace(/^\/+|\/+$/g, "");
  newBlankItem(kind, clean || undefined);
}

function openCodelistPicker(currentText, setValue) {
  openRefPicker(
    {
      kind: "codelists",
      title: "Choose codelist",
      findLabel: "Find or create a codelist",
      placeholder: "Search codelists, or type a new name…",
      emptyText: "This tree has no codelists yet.",
      refValue: (c) => c.name || c.key,
      matchText: (c) => `${c.name || ""} ${c.label || ""} ${c.key}`,
      createLabel: (raw) => `＋ Add "${raw}" as a new codelist`,
      createConfirm: "isn't an existing codelist. Add it now?",
      onCreate: (raw) => openNewCodelistDialog(raw),
    },
    currentText,
    setValue
  );
}

function openMethodPicker(currentText, setValue) {
  openRefPicker(
    {
      kind: "methods",
      title: "Choose method",
      findLabel: "Find or create a method",
      placeholder: "Search methods, or type a new path (e.g. adsl/trtsdt)…",
      emptyText: "This tree has no methods yet.",
      refValue: (m) => m.key,
      matchText: (m) => `${m.key} ${m.label || ""} ${m.name || ""}`,
      createLabel: (raw) => `＋ Add "${raw}" as a new method`,
      createConfirm: "isn't an existing method. Add it now?",
      onCreate: (raw) => startNewBlankRef("methods", raw),
    },
    currentText,
    setValue
  );
}

function openCommentPicker(currentText, setValue) {
  openRefPicker(
    {
      kind: "comments",
      title: "Choose comment",
      findLabel: "Find or create a comment",
      placeholder: "Search comments, or type a new path (e.g. adsl__usubjid)…",
      emptyText: "This tree has no comments yet.",
      refValue: (c) => c.key,
      matchText: (c) => `${c.key} ${c.label || ""}`,
      createLabel: (raw) => `＋ Add "${raw}" as a new comment`,
      createConfirm: "isn't an existing comment. Add it now?",
      onCreate: (raw) => startNewBlankRef("comments", raw),
    },
    currentText,
    setValue
  );
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function applyTreeIdentity() {
  // The only way to tell two `define edit` tabs on different studies apart - both the
  // browser tab title and the in-page sidebar header otherwise just say "define edit".
  // Best-effort throughout: an old server without /api/info, or a study.yaml that
  // hasn't been filled in yet, just falls back to the generic title rather than erroring.
  let source = null;
  try {
    source = (await API.info()).source;
  } catch {
    /* no-op */
  }
  let studyName = null;
  let protocolName = null;
  try {
    const study = await API.get("study", "study");
    const s = study.data && study.data.study;
    studyName = s && s.name;
    protocolName = s && s.protocol_name;
  } catch {
    /* no-op */
  }

  const label = [studyName, protocolName].filter(Boolean).join(" - ");
  document.title = label ? `${label} - define edit` : "define edit";

  const header = document.getElementById("sidebar-header");
  if (!header) return;
  clear(header);
  header.appendChild(el("div", { class: "sidebar-header-title" }, label || "define edit"));
  if (source) {
    header.appendChild(el("div", { class: "sidebar-header-path", title: source }, source));
  }
}

// Plain links, not fetch()-driven buttons: /api/render/xml and /api/render/html each
// return the whole rendered document directly (Content-Type: application/xml or
// text/html), so target="_blank" is the entire implementation - the browser's own tab
// renders or downloads it, right-click/middle-click "open in new tab" both work for
// free, and a build failure (LinkError -> 422) shows up as the browser's own error
// page in that tab rather than needing to be caught and displayed here.
function renderSidebarActions() {
  const box = document.getElementById("sidebar-actions");
  if (!box) return;
  clear(box);
  box.appendChild(el("a", { class: "sidebar-action-link", href: "/api/render/xml", target: "_blank", title: "Build define.xml from the current tree and open it" }, "View define.xml"));
  const htmlLink = el("a", { class: "sidebar-action-link", href: "/api/render/html", target: "_blank", title: "Build define.xml and render define.html from it" }, "View define.html");
  box.appendChild(htmlLink);

  // The stylesheet picker only appears when defineyaml/stylesheets/ holds more than
  // one *.xsl (a house variant dropped in beside the bundled one). Fetched after the
  // links are already up, so a slow/failed call just leaves the plain "View
  // define.html" link pointing at the default stylesheet.
  apiGet("/api/render/stylesheets")
    .then((sheets) => {
      if (!Array.isArray(sheets) || sheets.length < 2) return;
      const sel = el("select", {
        class: "sidebar-action-select",
        title: "Which XSLT stylesheet renders define.html",
        onchange: () => {
          htmlLink.href = `/api/render/html?stylesheet=${encodeURIComponent(sel.value)}`;
        },
      }, sheets.map((s) => el("option", { value: s.name }, `${s.label}${s.default ? " - default" : ""}`)));
      const initial = (sheets.find((s) => s.default) || sheets[0]).name;
      sel.value = initial;
      htmlLink.href = `/api/render/html?stylesheet=${encodeURIComponent(initial)}`;
      htmlLink.after(sel);
    })
    .catch(() => {});
  // A separate window, not a tab in this one: CT / standards lookup is independent of
  // any one define/ tree (NCI EVS downloads and the local standards folder are global,
  // per-machine), and a statistician plausibly wants it open alongside more than one
  // `define edit` window.
  box.appendChild(
    el(
      "a",
      { class: "sidebar-action-link", href: "/cdisc-viewer", target: "cdisc-standards-viewer", title: "Browse Controlled Terminology (NCI EVS) and a local folder of CDISC standards CSVs" },
      "Standards Viewer"
    )
  );

  // Switch to a different define tree without restarting the server - the launcher
  // (renderSetup) opens over the editor; picking a tree reloads onto it.
  box.appendChild(
    el(
      "a",
      {
        class: "sidebar-action-link",
        href: "#",
        title: "Open a different define tree, or create one",
        onclick: (e) => {
          e.preventDefault();
          if (state.dirty && !confirm("Leave this tree? Unsaved changes will be lost.")) return;
          clearTimeout(autosaveTimer);
          state.dirty = false;
          currentSave = null;
          renderSetup();
        },
      },
      "Open another tree",
    ),
  );
}

async function boot() {
  // First run (bare `define`, no remembered tree): the server is up but has no tree -
  // show the folder picker instead of the editor, then this page reloads once a tree
  // is chosen.
  let setup = { needs_setup: false };
  try {
    setup = await API.setupStatus();
  } catch {
    /* old server without the route - assume a tree is open */
  }
  if (setup.needs_setup) {
    await renderSetup();
    return;
  }

  await applyTreeIdentity();
  renderSidebarActions();
  state.kinds = await API.kinds();
  for (const meta of state.kinds) {
    await loadKindItems(meta.kind);
  }
  renderSidebar();

  // Restore autosave preference and the last-opened object, per source tree
  // (server.py's /api/state, persisted to ~/.config/defineyaml/editor-state.json -
  // see webui/state.py). Best-effort: a missing/unreadable object just leaves the
  // editor on the empty state, same as a fresh install.
  try {
    const saved = await API.getEditorState();
    state.autosave = !!saved.autosave;
    Object.assign(listViewState, saved.list_views || {});
    if (saved.kind && saved.key) {
      const items = state.itemsByKind[saved.kind] || [];
      if (items.some((i) => i.key === saved.key)) {
        await selectItem(saved.kind, saved.key);
      }
    }
  } catch {
    // no saved state yet - nothing to restore
  }
  if (!state.selection) renderEmptyState();
}

boot().catch((err) => {
  showStatus(false, describeError(err));
  renderEmptyState("Couldn't load this tree - check the server, then reload.");
});
