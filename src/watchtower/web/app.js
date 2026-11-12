// This dashboard deliberately contains no provider credentials or provider
// parsing. It requests Watchtower-owned JSON from the existing local API.
const TICKER_PATTERN = /^[A-Za-z][A-Za-z0-9.-]{0,9}$/;
const WATCHLIST_KEY = "watchtower.local-watchlist.v1";
const SELECTED_TICKER_KEY = "watchtower.local-selected-ticker.v1";

const elements = {
  form: document.querySelector("#watchlist-form"),
  input: document.querySelector("#ticker-input"),
  inputError: document.querySelector("#ticker-error"),
  watchlist: document.querySelector("#watchlist"),
  watchlistEmpty: document.querySelector("#watchlist-empty"),
  emptyState: document.querySelector("#empty-state"),
  loadingState: document.querySelector("#loading-state"),
  loadingTitle: document.querySelector("#loading-title"),
  errorState: document.querySelector("#error-state"),
  errorTitle: document.querySelector("#error-title"),
  errorDetail: document.querySelector("#error-detail"),
  retryButton: document.querySelector("#retry-button"),
  snapshot: document.querySelector("#snapshot"),
  refreshButton: document.querySelector("#refresh-button"),
};

const state = {
  watchlist: loadWatchlist(),
  selectedTicker: null,
};
state.selectedTicker = loadSelectedTicker(state.watchlist);

function loadWatchlist() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(WATCHLIST_KEY) || "[]");
    return Array.isArray(stored)
      ? stored.filter((ticker) => typeof ticker === "string" && TICKER_PATTERN.test(ticker))
      : [];
  } catch {
    // A malformed browser value should not prevent the dashboard from loading.
    return [];
  }
}

function saveWatchlist() {
  window.localStorage.setItem(WATCHLIST_KEY, JSON.stringify(state.watchlist));
}

function loadSelectedTicker(watchlist) {
  try {
    const stored = normalizeTicker(window.localStorage.getItem(SELECTED_TICKER_KEY) || "");
    // Prefer the user's previous selection. For an older saved watchlist that
    // predates this key, select its first ticker so startup shows useful data.
    if (watchlist.includes(stored)) return stored;
    return watchlist[0] || null;
  } catch {
    return watchlist[0] || null;
  }
}

function saveSelectedTicker() {
  if (state.selectedTicker === null) {
    window.localStorage.removeItem(SELECTED_TICKER_KEY);
    return;
  }
  window.localStorage.setItem(SELECTED_TICKER_KEY, state.selectedTicker);
}

function normalizeTicker(value) {
  return value.trim().toUpperCase();
}

function setInputError(message = "") {
  elements.inputError.textContent = message;
  elements.inputError.hidden = !message;
}

function renderWatchlist() {
  elements.watchlist.replaceChildren();
  elements.watchlistEmpty.hidden = state.watchlist.length > 0;

  for (const ticker of state.watchlist) {
    const item = document.createElement("li");
    item.className = "watchlist-item";

    const selectButton = document.createElement("button");
    selectButton.className = "watchlist-select";
    selectButton.textContent = ticker;
    selectButton.setAttribute("aria-current", String(ticker === state.selectedTicker));
    selectButton.addEventListener("click", () => selectTicker(ticker));

    const removeButton = document.createElement("button");
    removeButton.className = "watchlist-remove";
    removeButton.type = "button";
    removeButton.textContent = "Remove";
    removeButton.setAttribute("aria-label", `Remove ${ticker} from watchlist`);
    removeButton.addEventListener("click", () => removeTicker(ticker));

    item.append(selectButton, removeButton);
    elements.watchlist.append(item);
  }
}

function removeTicker(ticker) {
  const removedSelectedTicker = state.selectedTicker === ticker;
  state.watchlist = state.watchlist.filter((item) => item !== ticker);
  saveWatchlist();

  if (removedSelectedTicker) {
    state.selectedTicker = state.watchlist[0] || null;
    saveSelectedTicker();
    if (state.selectedTicker === null) showState("empty");
  }
  renderWatchlist();
  if (removedSelectedTicker && state.selectedTicker !== null) {
    loadSnapshot(state.selectedTicker);
  }
}

function selectTicker(ticker) {
  state.selectedTicker = ticker;
  saveSelectedTicker();
  renderWatchlist();
  loadSnapshot(ticker);
}

function showState(name) {
  elements.emptyState.hidden = name !== "empty";
  elements.loadingState.hidden = name !== "loading";
  elements.errorState.hidden = name !== "error";
  elements.snapshot.hidden = name !== "snapshot";
}

async function loadSnapshot(ticker, { forceRefresh = false } = {}) {
  showState("loading");
  elements.loadingTitle.textContent = `Building ${ticker}'s research snapshot`;

  try {
    const refresh = forceRefresh ? "?refresh=true" : "";
    const response = await fetch(`/companies/${encodeURIComponent(ticker)}/snapshot${refresh}`);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Watchtower returned ${response.status}.`);
    }

    renderSnapshot(await response.json());
    showState("snapshot");
  } catch (error) {
    elements.errorTitle.textContent = `Watchtower could not load ${ticker}.`;
    elements.errorDetail.textContent = error instanceof Error ? error.message : "Unknown error.";
    showState("error");
  }
}

function formatTimestamp(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatPrice(value, currency) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value) {
  if (value === null || value === undefined) return "Not available";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function appendSourceLinks(container, urls, label) {
  if (!urls.length) return;
  const links = document.createElement("div");
  links.className = "evidence-links";
  urls.forEach((url, index) => {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = `${label} ${index + 1}`;
    links.append(link);
  });
  container.append(links);
}

function renderSnapshot(snapshot) {
  document.querySelector("#company-ticker").textContent = snapshot.ticker;
  document.querySelector("#company-name").textContent = snapshot.company_name;
  document.querySelector("#company-cik").textContent = `SEC CIK ${snapshot.cik}`;
  renderSnapshotStatus(snapshot);

  const signal = snapshot.research_signal;
  document.querySelector("#signal-score").textContent = signal.attention_score;
  document.querySelector("#signal-level").textContent = signal.level.replaceAll("_", " ");
  document.querySelector("#signal-explanation").textContent = signal.explanation;
  document.querySelector("#signal-limitation").textContent = signal.limitation;

  const evidence = document.querySelector("#signal-evidence");
  evidence.replaceChildren();
  if (!signal.evidence.length) {
    const item = document.createElement("li");
    item.textContent = "No weighted activity is available in this snapshot.";
    evidence.append(item);
  }
  signal.evidence.forEach((entry) => {
    const item = document.createElement("li");
    const header = document.createElement("div");
    header.className = "evidence-header";
    const summary = document.createElement("span");
    summary.textContent = entry.summary;
    const points = document.createElement("span");
    points.className = "points";
    points.textContent = `+${entry.points} points`;
    header.append(summary, points);
    item.append(header);
    appendSourceLinks(item, entry.source_urls, entry.source_provider);
    evidence.append(item);
  });

  const price = snapshot.price.data;
  document.querySelector("#latest-close").textContent = formatPrice(price.latest_close, price.currency);
  const change = document.querySelector("#daily-change");
  change.textContent = formatPercent(price.change_percent);
  change.className = price.change_percent > 0 ? "positive" : price.change_percent < 0 ? "negative" : "neutral";
  document.querySelector("#price-date").textContent = price.price_date;
  document.querySelector("#price-retrieved").textContent = formatTimestamp(snapshot.price.source.retrieved_at);

  renderFilings(snapshot.filings.items, snapshot.filings.source.retrieved_at);
  renderNews(snapshot.news.items, snapshot.news.source.retrieved_at);
}

function renderSnapshotStatus(snapshot) {
  const status = document.querySelector("#snapshot-status");
  const asOf = formatTimestamp(snapshot.generated_at);
  const labels = {
    live: `Live sources · last refreshed ${asOf}`,
    cached: `Cached snapshot · last refreshed ${asOf}`,
    stale: `Stale snapshot · sources unavailable · last refreshed ${asOf}`,
  };
  status.textContent = labels[snapshot.snapshot_status] || `Snapshot generated ${asOf}`;
  status.className = `snapshot-status status-${snapshot.snapshot_status}`;
}

function renderFilings(filings, retrievedAt) {
  document.querySelector("#filings-retrieved").textContent = `Retrieved ${formatTimestamp(retrievedAt)}`;
  const list = document.querySelector("#filings");
  list.replaceChildren();
  if (!filings.length) {
    const item = document.createElement("li");
    item.textContent = "No recent 8-K filings were returned.";
    list.append(item);
    return;
  }
  filings.forEach((filing) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = filing.document_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = `${filing.form} filed ${filing.filing_date}`;
    const detail = document.createElement("small");
    detail.textContent = `Accession ${filing.accession_number}`;
    item.append(link, detail);
    list.append(item);
  });
}

function renderNews(headlines, retrievedAt) {
  document.querySelector("#news-retrieved").textContent = `Retrieved ${formatTimestamp(retrievedAt)}`;
  const list = document.querySelector("#news");
  list.replaceChildren();
  if (!headlines.length) {
    const item = document.createElement("li");
    item.textContent = "No associated headlines were returned.";
    list.append(item);
    return;
  }
  headlines.forEach((headline) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = headline.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = headline.title;
    const snippet = document.createElement("p");
    snippet.textContent = headline.snippet || "No source snippet available.";
    const detail = document.createElement("small");
    detail.textContent = `${headline.publisher} · ${formatTimestamp(headline.published_at)}`;
    item.append(link, snippet, detail);
    list.append(item);
  });
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const ticker = normalizeTicker(elements.input.value);
  if (!TICKER_PATTERN.test(ticker)) {
    setInputError("Enter a ticker beginning with a letter, up to ten characters.");
    elements.input.focus();
    return;
  }
  if (!state.watchlist.includes(ticker)) {
    state.watchlist.push(ticker);
    saveWatchlist();
  }
  elements.input.value = "";
  setInputError();
  selectTicker(ticker);
});

elements.retryButton.addEventListener("click", () => {
  if (state.selectedTicker) loadSnapshot(state.selectedTicker, { forceRefresh: true });
});
elements.refreshButton.addEventListener("click", () => {
  if (state.selectedTicker) loadSnapshot(state.selectedTicker, { forceRefresh: true });
});

renderWatchlist();
if (state.selectedTicker !== null) loadSnapshot(state.selectedTicker);
