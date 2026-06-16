// Tiny vanilla-JS client for the RAG cost-optimized demo.

const $ = (sel) => document.querySelector(sel);

const els = {
  statusPill:  $("#statusPill"),
  kpiSaved:    $("#kpiSaved"),
  kpiNaive:    $("#kpiNaive"),
  kpiSmart:    $("#kpiSmart"),
  kpiChunks:   $("#kpiChunks"),
  kpiCache:    $("#kpiCache"),
  kpiModel:    $("#kpiModel"),
  btnNaive:    $("#btnNaive"),
  btnSmart:    $("#btnSmart"),
  btnClear:    $("#btnClear"),
  btnReset:    $("#btnReset"),
  lastRun:     $("#lastRun"),
  corpusCount: $("#corpusCount"),
  docList:     $("#docList"),
  docId:       $("#docId"),
  docText:     $("#docText"),
  editorMeta:  $("#editorMeta"),
  btnSave:     $("#btnSave"),
  btnDelete:   $("#btnDelete"),
  btnNew:      $("#btnNew"),
  queryInput:  $("#queryInput"),
  btnQuery:    $("#btnQuery"),
  queryAnswer: $("#queryAnswer"),
  queryHits:   $("#queryHits"),
  presetRow:    $("#presetRow"),
  btnMutate5:   $("#btnMutate5"),
  btnMutate25:  $("#btnMutate25"),
  btnRemoveSynth: $("#btnRemoveSynth"),
  genResult:    $("#genResult"),
  churnPct:     $("#churnPct"),
  refreshes:    $("#refreshes"),
  btnProject:   $("#btnProject"),
  calibrationLine: $("#calibrationLine"),
  projectionTable: $("#projectionTable").querySelector("tbody"),
};

const state = {
  docs: [],
  selected: null,
};

const fmtUSD = (n) => "$" + (n || 0).toFixed(6);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }
  return res.json();
}

// ---- Status / KPIs --------------------------------------------------------

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    const realBits = [
      s.real_embeddings ? "real embeddings" : "simulated embeddings",
      s.ai_search ? "AI Search" : null,
      s.foundry ? (s.foundry_agent_configured ? "Foundry agent" : "Foundry project") : null,
    ].filter(Boolean).join(" · ");
    els.statusPill.textContent = realBits;
    els.statusPill.classList.toggle("ok", s.real_embeddings);
    els.statusPill.classList.toggle("azure", s.real_embeddings || s.ai_search || s.foundry);
    const tip = [
      s.real_embeddings ? `Azure OpenAI: ${s.azure_openai_endpoint}` : "Azure OpenAI: not configured",
      s.ai_search       ? `AI Search: ${s.azure_ai_search_endpoint} (index: ${s.azure_ai_search_index})` : "AI Search: not configured",
      s.foundry         ? `Foundry: ${s.foundry_project_endpoint}` + (s.foundry_agent_configured ? "" : " (agent ID not set)") : "Foundry: not configured",
    ].join("\n");
    els.statusPill.title = tip;
    els.kpiModel.textContent = s.embedding_model;
    els.kpiChunks.textContent = s.index_stats.total_chunks;
    els.kpiCache.textContent  = s.cache_stats.cached_chunks;
    els.kpiSaved.textContent  = fmtUSD(s.session_totals.saved);
    els.kpiNaive.textContent  = fmtUSD(s.session_totals.naive_spent);
    els.kpiSmart.textContent  = fmtUSD(s.session_totals.incremental_spent);
  } catch (e) {
    els.statusPill.textContent = "error";
    console.error(e);
  }
}

// ---- Corpus list / editor -------------------------------------------------

async function refreshDocs(keepSelection = true) {
  const resp = await api("/api/corpus?limit=50");
  state.docs = resp.items;
  state.totalDocs = resp.total;
  els.corpusCount.textContent = resp.total > resp.items.length
    ? `showing ${resp.items.length} of ${resp.total.toLocaleString()}`
    : `${resp.total.toLocaleString()} docs`;
  els.docList.innerHTML = "";
  for (const d of state.docs) {
    const li = document.createElement("li");
    li.dataset.docId = d.doc_id;
    const stats = resp.with_stats
      ? `${d.chunk_count} chunks · ${d.token_count.toLocaleString()} tokens`
      : `${d.token_count.toLocaleString()} tokens`;
    li.innerHTML = `
      <span class="doc-title">${escapeHtml(d.title)}</span>
      <span class="doc-meta">${d.doc_id} · ${stats}</span>
    `;
    li.addEventListener("click", () => selectDoc(d.doc_id));
    if (keepSelection && state.selected === d.doc_id) li.classList.add("selected");
    els.docList.appendChild(li);
  }
  if (!keepSelection || !state.docs.find(d => d.doc_id === state.selected)) {
    if (state.docs.length) selectDoc(state.docs[0].doc_id);
    else clearEditor();
  }
}

async function selectDoc(docId) {
  state.selected = docId;
  // Always fetch the full document (the list view may have skipped chunk stats).
  let doc;
  try {
    doc = await api(`/api/corpus/${encodeURIComponent(docId)}`);
  } catch (e) {
    return;
  }
  els.docId.value = doc.doc_id;
  els.docId.disabled = true;
  els.docText.value = doc.text;
  els.editorMeta.textContent =
    `hash=${doc.hash.slice(0,12)}… · ${doc.token_count.toLocaleString()} tokens · ${doc.chunk_count} chunks`;
  document.querySelectorAll(".doc-list li").forEach(li => {
    li.classList.toggle("selected", li.dataset.docId === docId);
  });
}

function clearEditor() {
  state.selected = null;
  els.docId.value = "";
  els.docId.disabled = false;
  els.docText.value = "";
  els.editorMeta.textContent = "";
}

async function saveDoc() {
  const id = els.docId.value.trim();
  const text = els.docText.value;
  if (!id) return alert("Please provide a doc_id (a-z, 0-9, _, -).");
  try {
    await api(`/api/corpus/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ doc_id: id, text }),
    });
    state.selected = id;
    await refreshDocs();
    flash(els.btnSave, "Saved");
  } catch (e) {
    alert(e.message);
  }
}

async function deleteDoc() {
  if (!state.selected) return;
  if (!confirm(`Delete document "${state.selected}"?`)) return;
  await api(`/api/corpus/${encodeURIComponent(state.selected)}`, { method: "DELETE" });
  state.selected = null;
  await refreshDocs(false);
}

// ---- Re-index actions -----------------------------------------------------

function renderRun(report) {
  const cls = report.strategy;
  const savedLine = report.strategy === "incremental"
    ? `<span class="run-line">saved: <span class="run-cost saved">${fmtUSD(report.savings_usd)}</span> (${report.savings_pct.toFixed(1)}%)</span>`
    : "";
  els.lastRun.innerHTML = `
    <span class="run-line"><span class="run-strategy ${cls}">${report.strategy.toUpperCase()}</span> &nbsp; ${report.elapsed_ms.toFixed(0)} ms</span>
    <span class="run-line">docs: ${report.documents_seen} (skipped ${report.documents_skipped}) · chunks: ${report.chunks_seen} (embedded ${report.chunks_embedded}, cache hit ${report.chunks_cache_hit})</span>
    <span class="run-line">tokens embedded: <b>${report.tokens_embedded.toLocaleString()}</b> &nbsp; / &nbsp; naive equivalent: ${report.tokens_would_have_embedded.toLocaleString()}</span>
    <span class="run-line">cost: <span class="run-cost ${report.strategy === 'naive' ? 'bad' : 'good'}">${fmtUSD(report.cost_usd)}</span> · naive-equivalent: <span class="run-cost bad">${fmtUSD(report.naive_equivalent_usd)}</span></span>
    ${savedLine}
    ${(report.notes || []).map(n => `<span class="run-line">• ${escapeHtml(n)}</span>`).join("")}
  `;
}

async function runReindex(kind, btn) {
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = "running…";
  try {
    const r = await api(`/api/index/${kind}`, { method: "POST" });
    renderRun(r);
    await refreshStatus();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

// ---- Query ----------------------------------------------------------------

async function runQuery() {
  const q = els.queryInput.value.trim();
  if (!q) return;
  els.btnQuery.disabled = true;
  els.queryAnswer.textContent = "searching…";
  els.queryHits.innerHTML = "";
  try {
    const r = await api("/api/query", {
      method: "POST",
      body: JSON.stringify({ q, k: 5 }),
    });
    els.queryAnswer.textContent = r.answer + (r.foundry_used ? "  (via Foundry agent)" : "");
    els.queryHits.innerHTML = "";
    for (const h of r.hits) {
      const li = document.createElement("li");
      li.innerHTML = `
        <div class="hit-meta">${h.doc_id} · ${h.chunk_id} · score=${h.score.toFixed(3)}</div>
        <div>${escapeHtml(truncate(h.text, 260))}</div>
      `;
      els.queryHits.appendChild(li);
    }
    if (!r.hits.length) {
      els.queryHits.innerHTML = "<li>No matches — try re-indexing first.</li>";
    }
  } catch (e) {
    els.queryAnswer.textContent = "error: " + e.message;
  } finally {
    els.btnQuery.disabled = false;
  }
}

// ---- Misc -----------------------------------------------------------------

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
function truncate(s, n) { return s.length > n ? s.slice(0, n) + "…" : s; }
function flash(btn, msg) {
  const orig = btn.textContent;
  btn.textContent = msg;
  setTimeout(() => (btn.textContent = orig), 900);
}

// ---- Scale Lab ------------------------------------------------------------

const fmtBig = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });

function fmtMoney(n) {
  if (!Number.isFinite(n)) return "$0";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return "$" + (n / 1_000_000).toFixed(2) + "M";
  if (abs >= 1_000)     return "$" + (n / 1_000).toFixed(2) + "K";
  if (abs >= 1)         return "$" + n.toFixed(2);
  return "$" + n.toFixed(4);
}

async function loadPresets() {
  let presets;
  try { presets = await api("/api/scale/presets"); }
  catch (e) { return; }
  els.presetRow.innerHTML = "";
  for (const [key, p] of Object.entries(presets)) {
    const b = document.createElement("button");
    b.className = "btn small";
    b.textContent = `${p.label} (${p.approx_size})`;
    b.title = `${p.doc_count.toLocaleString()} docs × ~${p.kb_per_doc} KB`;
    b.addEventListener("click", () => generateCorpus(key, b));
    els.presetRow.appendChild(b);
  }
}

async function generateCorpus(preset, btn) {
  if (!confirm(`Generate the "${preset}" corpus? This will clear the existing synthetic docs, cache, and index.`)) return;
  btn.disabled = true; const orig = btn.textContent; btn.textContent = "generating…";
  els.genResult.textContent = "generating documents…";
  try {
    const r = await api("/api/scale/generate", {
      method: "POST",
      body: JSON.stringify({ preset, clear_existing_synthetic: true }),
    });
    // After generation, clear cache + in-memory index so the next run is cold.
    await api("/api/index/clear", { method: "POST" });
    els.genResult.innerHTML =
      `<b>${r.documents_written.toLocaleString()}</b> docs written · ` +
      `<b>${r.mb_written} MB</b> · ${(r.elapsed_ms / 1000).toFixed(1)} s. ` +
      `Cache + index cleared — try "Naive" then "Smart Incremental" to see the savings story at scale.`;
    await refreshStatus();
    await refreshDocs(false);
  } catch (e) {
    els.genResult.textContent = "error: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

async function mutateRandom(pct, btn) {
  btn.disabled = true; const orig = btn.textContent; btn.textContent = "mutating…";
  try {
    const r = await api(`/api/corpus/mutate-random?percent=${pct}`, { method: "POST" });
    els.genResult.innerHTML =
      `Mutated <b>${r.mutated.toLocaleString()}</b> of ${r.of.toLocaleString()} docs ` +
      `(${r.percent}%). Run "Smart Incremental Re-index" now to see only the delta.`;
    await refreshDocs(true);
  } catch (e) {
    els.genResult.textContent = "error: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

async function removeSynthetic(btn) {
  if (!confirm("Delete all generated synthetic documents (keeps the seed docs)?")) return;
  btn.disabled = true; const orig = btn.textContent; btn.textContent = "removing…";
  try {
    const r = await api("/api/scale/remove-synthetic", { method: "POST" });
    await api("/api/index/clear", { method: "POST" });
    els.genResult.textContent = `Removed ${r.removed.toLocaleString()} synthetic docs. Cache + index cleared.`;
    await refreshDocs(false);
    await refreshStatus();
  } catch (e) {
    els.genResult.textContent = "error: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

async function runProjection() {
  const churn = parseFloat(els.churnPct.value);
  const refreshes = parseInt(els.refreshes.value, 10);
  els.btnProject.disabled = true;
  const orig = els.btnProject.textContent;
  els.btnProject.textContent = "calibrating…";
  try {
    const r = await api("/api/scale/project", {
      method: "POST",
      body: JSON.stringify({ churn_pct: churn, refreshes_per_year: refreshes }),
    });
    const c = r.calibration;
    els.calibrationLine.textContent =
      `Calibrated from ${c.sample_docs.toLocaleString()} docs / ${(c.sample_bytes / (1024 * 1024)).toFixed(2)} MB ` +
      `→ ${fmtBig(c.tokens_per_mb)} tokens/MB, ${c.avg_chunks_per_doc.toFixed(1)} chunks/doc. ` +
      `Pricing: $${(c.tokens_per_mb * 0)/1 || ""}` /* placeholder */;
    // Render table
    els.projectionTable.innerHTML = "";
    for (const row of r.rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><b>${row.label}</b></td>
        <td>${fmtBig(row.docs)}</td>
        <td>${fmtBig(row.tokens)}</td>
        <td class="col-naive">${fmtMoney(row.full_reindex_cost)}</td>
        <td class="col-smart">${fmtMoney(row.smart_reindex_cost_at_churn)}</td>
        <td class="col-naive">${fmtMoney(row.annual_naive)}</td>
        <td class="col-smart">${fmtMoney(row.annual_smart)}</td>
        <td class="col-saved">${fmtMoney(row.annual_saved)}</td>
      `;
      els.projectionTable.appendChild(tr);
    }
    // Cleaner calibration line (drop placeholder)
    els.calibrationLine.textContent =
      `Calibrated from ${c.sample_docs.toLocaleString()} docs / ${(c.sample_bytes / (1024 * 1024)).toFixed(2)} MB → ` +
      `${fmtBig(c.tokens_per_mb)} tokens/MB · ${c.avg_chunks_per_doc.toFixed(1)} chunks/doc · ` +
      `assuming ${churn}% daily churn × ${refreshes} refreshes/year.`;
  } catch (e) {
    els.calibrationLine.textContent = "error: " + e.message;
  } finally {
    els.btnProject.disabled = false;
    els.btnProject.textContent = orig;
  }
}

// ---- Wire up --------------------------------------------------------------

els.btnNaive.addEventListener("click", () => runReindex("naive", els.btnNaive));
els.btnSmart.addEventListener("click", () => runReindex("incremental", els.btnSmart));
els.btnClear.addEventListener("click", async () => {
  if (!confirm("Clear the cache and the in-memory index? (Corpus is not touched.)")) return;
  await api("/api/index/clear", { method: "POST" });
  await refreshStatus();
  els.lastRun.textContent = "Cleared. Next re-index will start cold.";
});
els.btnReset.addEventListener("click", async () => {
  if (!confirm("Replace the working corpus with the seed documents?")) return;
  await api("/api/corpus/reset", { method: "POST" });
  await refreshDocs(false);
});
els.btnSave.addEventListener("click", saveDoc);
els.btnDelete.addEventListener("click", deleteDoc);
els.btnNew.addEventListener("click", clearEditor);
els.btnQuery.addEventListener("click", runQuery);
els.queryInput.addEventListener("keydown", (e) => { if (e.key === "Enter") runQuery(); });

els.btnMutate5.addEventListener("click", () => mutateRandom(5, els.btnMutate5));
els.btnMutate25.addEventListener("click", () => mutateRandom(25, els.btnMutate25));
els.btnRemoveSynth.addEventListener("click", () => removeSynthetic(els.btnRemoveSynth));
els.btnProject.addEventListener("click", runProjection);

(async () => {
  await refreshStatus();
  await refreshDocs(false);
  await loadPresets();
  setInterval(refreshStatus, 5000);
})();
