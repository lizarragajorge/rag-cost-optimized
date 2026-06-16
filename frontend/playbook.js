const byId = (id) => document.getElementById(id);

const ui = {
  statusStamp: byId("statusStamp"),
  statusEmbedding: byId("statusEmbedding"),
  statusSearch: byId("statusSearch"),
  statusFoundry: byId("statusFoundry"),
  statusModel: byId("statusModel"),
  riskList: byId("riskList"),
  btnRefreshStatus: byId("btnRefreshStatus"),
  tokensInput: byId("tokensInput"),
  churnInput: byId("churnInput"),
  refreshInput: byId("refreshInput"),
  btnEstimate: byId("btnEstimate"),
  smallNaiveRun: byId("smallNaiveRun"),
  smallNaiveAnnual: byId("smallNaiveAnnual"),
  smallSmartRun: byId("smallSmartRun"),
  smallSmartAnnual: byId("smallSmartAnnual"),
  largeNaiveRun: byId("largeNaiveRun"),
  largeNaiveAnnual: byId("largeNaiveAnnual"),
  largeSmartRun: byId("largeSmartRun"),
  largeSmartAnnual: byId("largeSmartAnnual"),
  smallSavingsAnnual: byId("smallSavingsAnnual"),
  largeSavingsAnnual: byId("largeSavingsAnnual"),
  modelDeltaAnnual: byId("modelDeltaAnnual"),
};

async function getStatus() {
  const res = await fetch("/api/status", {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`Status fetch failed: ${res.status}`);
  }
  return res.json();
}

function money(v) {
  return `$${Number(v || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function addRisk(kind, text) {
  const li = document.createElement("li");
  li.className = kind;
  li.textContent = text;
  ui.riskList.appendChild(li);
}

function renderStatus(s) {
  const now = new Date();
  ui.statusStamp.textContent = `updated ${now.toLocaleTimeString()}`;

  ui.statusEmbedding.textContent = s.real_embeddings
    ? "Real Azure OpenAI embeddings"
    : "Simulated embeddings";

  ui.statusSearch.textContent = s.ai_search
    ? `AI Search connected (${s.azure_ai_search_index})`
    : "AI Search not connected";

  ui.statusFoundry.textContent = s.foundry
    ? (s.foundry_agent_configured ? "Foundry agent path active" : "Foundry project set, agent missing")
    : "Foundry path disabled";

  ui.statusModel.textContent = `${s.embedding_model} | cached chunks: ${s.cache_stats.cached_chunks}`;

  ui.riskList.innerHTML = "";

  if (!s.ai_search) {
    addRisk("warn", "AI Search is off. Copilot Studio knowledge grounding will not be available.");
  } else {
    addRisk("ok", "AI Search is active. Keep one stable index schema for Copilot Studio mapping.");
  }

  if (!s.real_embeddings) {
    addRisk("warn", "Embeddings are simulated. Use real embeddings in production to validate quality and spend.");
  } else {
    addRisk("ok", "Real embeddings enabled. You can track actual token-driven costs.");
  }

  if ((s.embedding_model || "").toLowerCase().includes("large")) {
    addRisk("warn", "Large embedding model detected. Validate whether smaller model can meet quality to cut cost.");
  } else {
    addRisk("ok", "Smaller embedding model in use. Good default for cost-performance.");
  }

  if (!s.foundry_agent_configured) {
    addRisk("warn", "Foundry agent ID is not configured. Queries may bypass agent behavior.");
  } else {
    addRisk("ok", "Foundry agent is configured. Good for end-to-end reliability checks.");
  }

  if (s.session_totals.incremental_spent > s.session_totals.naive_spent) {
    addRisk("warn", "Incremental runs currently spending more than naive. Check churn assumptions and cache misses.");
  } else {
    addRisk("ok", "Incremental spending trend is lower than naive in this session.");
  }
}

function computeEstimate() {
  const tokens = Math.max(Number(ui.tokensInput.value || 0), 0);
  const churn = Math.min(Math.max(Number(ui.churnInput.value || 0), 0), 100) / 100;
  const refreshes = Math.max(Number(ui.refreshInput.value || 0), 1);

  const SMALL_RATE = 0.02;
  const LARGE_RATE = 0.13;

  const smallNaiveRun = (tokens / 1_000_000) * SMALL_RATE;
  const smallSmartRun = (tokens * churn / 1_000_000) * SMALL_RATE;
  const largeNaiveRun = (tokens / 1_000_000) * LARGE_RATE;
  const largeSmartRun = (tokens * churn / 1_000_000) * LARGE_RATE;

  const smallNaiveAnnual = smallNaiveRun * refreshes;
  const smallSmartAnnual = smallSmartRun * refreshes;
  const largeNaiveAnnual = largeNaiveRun * refreshes;
  const largeSmartAnnual = largeSmartRun * refreshes;

  ui.smallNaiveRun.textContent = money(smallNaiveRun);
  ui.smallNaiveAnnual.textContent = money(smallNaiveAnnual);
  ui.smallSmartRun.textContent = money(smallSmartRun);
  ui.smallSmartAnnual.textContent = money(smallSmartAnnual);

  ui.largeNaiveRun.textContent = money(largeNaiveRun);
  ui.largeNaiveAnnual.textContent = money(largeNaiveAnnual);
  ui.largeSmartRun.textContent = money(largeSmartRun);
  ui.largeSmartAnnual.textContent = money(largeSmartAnnual);

  ui.smallSavingsAnnual.textContent = money(Math.max(smallNaiveAnnual - smallSmartAnnual, 0));
  ui.largeSavingsAnnual.textContent = money(Math.max(largeNaiveAnnual - largeSmartAnnual, 0));
  ui.modelDeltaAnnual.textContent = money(Math.max(largeNaiveAnnual - smallNaiveAnnual, 0));
}

async function refreshStatus() {
  try {
    const s = await getStatus();
    renderStatus(s);
  } catch (err) {
    ui.statusStamp.textContent = "status unavailable";
    ui.riskList.innerHTML = "";
    addRisk("warn", "Could not read /api/status. Start backend and retry.");
    console.error(err);
  }
}

ui.btnRefreshStatus.addEventListener("click", refreshStatus);
ui.btnEstimate.addEventListener("click", computeEstimate);

document.querySelectorAll(".clickable-card").forEach((card) => {
  const href = card.getAttribute("data-href");
  if (!href) return;
  card.addEventListener("click", () => {
    window.location.href = href;
  });
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      window.location.href = href;
    }
  });
});

refreshStatus();
computeEstimate();
