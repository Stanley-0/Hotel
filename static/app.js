(() => {
  const form = document.getElementById("search-form");
  const checkIn = document.getElementById("check_in");
  const checkOut = document.getElementById("check_out");
  const adults = document.getElementById("adults");
  const rooms = document.getElementById("rooms");
  const submit = document.getElementById("submit");
  const submitLabel = submit.querySelector(".button-label");
  const formError = document.getElementById("form-error");
  const summary = document.getElementById("stay-summary");
  const body = document.getElementById("results-body");
  const meta = document.getElementById("results-meta");
  const download = document.getElementById("download");
  const headers = document.querySelectorAll("th[aria-sort]");

  const DAY = 86_400_000;
  const state = { results: [], query: null, sort: { key: null, dir: "ascending" } };

  const toISO = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
  const parseISO = (s) => (s ? new Date(`${s}T00:00:00`) : null);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  function nightsBetween() {
    const a = parseISO(checkIn.value);
    const b = parseISO(checkOut.value);
    return a && b ? Math.round((b - a) / DAY) : 0;
  }

  function updateSummary() {
    const nights = nightsBetween();
    if (nights < 1) {
      summary.textContent = "Pick your dates to see the length of stay.";
      return;
    }
    const people = Number(adults.value) || 0;
    const roomCount = Number(rooms.value) || 0;
    summary.innerHTML = "";
    const strong = document.createElement("strong");
    strong.textContent = plural(nights, "night");
    summary.append(strong, ` · ${plural(people, "person").replace("persons", "people")} · ${plural(roomCount, "room")}`);
  }

  function setDefaultDates() {
    const start = new Date(Date.now() + 14 * DAY);
    checkIn.value = toISO(start);
    checkOut.value = toISO(new Date(start.getTime() + 3 * DAY));
    checkOut.min = toISO(new Date(start.getTime() + DAY));
  }

  checkIn.addEventListener("change", () => {
    const start = parseISO(checkIn.value);
    if (!start) return;
    const minOut = new Date(start.getTime() + DAY);
    checkOut.min = toISO(minOut);
    if (!checkOut.value || parseISO(checkOut.value) <= start) checkOut.value = toISO(minOut);
    updateSummary();
  });
  [checkOut, adults, rooms].forEach((el) => el.addEventListener("input", updateSummary));

  function showError(message) {
    formError.textContent = message;
    formError.hidden = !message;
  }

  function validate(data) {
    form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
    const fail = (el, msg) => {
      el.setAttribute("aria-invalid", "true");
      el.focus();
      return msg;
    };
    if (!data.location) return fail(form.location, "Enter a location.");
    if (!data.check_in) return fail(checkIn, "Choose a check-in date.");
    if (!data.check_out || nightsBetween() < 1) return fail(checkOut, "Check-out must be after check-in.");
    if (!Number.isInteger(data.adults) || data.adults < 1) return fail(adults, "Enter how many people are staying.");
    if (!Number.isInteger(data.rooms) || data.rooms < 1) return fail(rooms, "Enter how many rooms you need.");
    if (data.rooms > data.adults) return fail(rooms, "You need at least one person per room.");
    return "";
  }

  function formatMoney(value, currency) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
    } catch {
      return `${currency} ${value.toLocaleString()}`;
    }
  }

  function renderMessage(text) {
    body.innerHTML = "";
    const row = body.insertRow();
    row.className = "empty-row";
    const cell = row.insertCell();
    cell.colSpan = 5;
    cell.textContent = text;
  }

  function renderSkeleton() {
    body.innerHTML = "";
    const widths = ["70%", "40px", "80px", "90px"];
    for (let i = 0; i < 6; i++) {
      const row = body.insertRow();
      row.insertCell().className = "col-index";
      widths.forEach((w, idx) => {
        const cell = row.insertCell();
        if (idx > 0) cell.className = "num";
        const bar = document.createElement("span");
        bar.className = "skeleton";
        bar.style.width = w;
        cell.append(bar);
      });
    }
  }

  function sortedResults() {
    const { key, dir } = state.sort;
    if (!key) return state.results;
    const factor = dir === "ascending" ? 1 : -1;
    return [...state.results].sort((a, b) => {
      const x = a[key];
      const y = b[key];
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * factor;
    });
  }

  function isBookingUrl(url) {
    try {
      const host = new URL(url).hostname;
      return host === "booking.com" || host.endsWith(".booking.com");
    } catch {
      return false;
    }
  }

  function renderResults() {
    const { currency } = state.query;
    body.innerHTML = "";
    sortedResults().forEach((item, i) => {
      const row = body.insertRow();

      const idx = row.insertCell();
      idx.className = "col-index";
      idx.textContent = String(i + 1);

      const nameCell = row.insertCell();
      const name = document.createElement(item.url && isBookingUrl(item.url) ? "a" : "span");
      name.className = "hotel-name";
      name.textContent = item.name;
      if (name.tagName === "A") {
        name.href = item.url;
        name.target = "_blank";
        name.rel = "noopener noreferrer";
      }
      nameCell.append(name);

      const ratingCell = row.insertCell();
      ratingCell.className = "num";
      if (item.rating == null) {
        ratingCell.innerHTML = '<span class="muted">—</span>';
      } else {
        const badge = document.createElement("span");
        badge.className = item.rating >= 8.5 ? "rating high" : "rating";
        badge.textContent = item.rating.toFixed(1);
        ratingCell.append(badge);
      }

      const nightly = row.insertCell();
      nightly.className = "num";
      nightly.textContent = formatMoney(item.price_per_night, currency);

      const total = row.insertCell();
      total.className = "num total";
      total.textContent = formatMoney(item.total_price, currency);
    });
  }

  function updateSortHeaders() {
    headers.forEach((th) => {
      const key = th.querySelector("button").dataset.sort;
      th.setAttribute("aria-sort", key === state.sort.key ? state.sort.dir : "none");
    });
  }

  headers.forEach((th) => {
    th.querySelector("button").addEventListener("click", (e) => {
      const key = e.currentTarget.dataset.sort;
      state.sort =
        state.sort.key === key
          ? { key, dir: state.sort.dir === "ascending" ? "descending" : "ascending" }
          : { key, dir: key === "rating" ? "descending" : "ascending" };
      updateSortHeaders();
      if (state.results.length) renderResults();
    });
  });

  function setLoading(loading) {
    submit.disabled = loading;
    submit.setAttribute("aria-busy", String(loading));
    submitLabel.textContent = loading ? "Scraping Booking.com…" : "Search Booking.com";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = {
      location: form.location.value.trim(),
      check_in: checkIn.value,
      check_out: checkOut.value,
      adults: Number(adults.value),
      rooms: Number(rooms.value),
      currency: form.currency.value,
    };
    const problem = validate(data);
    showError(problem);
    if (problem) return;

    setLoading(true);
    download.disabled = true;
    meta.textContent = "Opening Chrome and reading listings. This usually takes 20–60 seconds.";
    renderSkeleton();

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "Search failed. Please try again.");

      state.results = payload.results;
      state.query = payload.query;
      const q = payload.query;
      meta.textContent = `${plural(state.results.length, "property")} in ${q.location} · ${plural(q.nights, "night")} · prices in ${q.currency}`.replace("propertys", "properties");

      if (state.results.length) {
        renderResults();
        download.disabled = false;
      } else {
        renderMessage("Booking.com returned no available properties for this search.");
      }
    } catch (error) {
      state.results = [];
      showError(error.message);
      meta.textContent = "The last search didn't complete.";
      renderMessage("No results to show.");
    } finally {
      setLoading(false);
    }
  });

  download.addEventListener("click", () => {
    if (!state.results.length) return;
    const { currency, location } = state.query;
    const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [
      ["Accommodation", "Rating", `Price per night (${currency})`, `Total stay (${currency})`, "Link"],
      ...sortedResults().map((r) => [r.name, r.rating ?? "", r.price_per_night, r.total_price, r.url ?? ""]),
    ].map((row) => row.map(escape).join(","));
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `staysheet-${location.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  });

  setDefaultDates();
  updateSummary();
})();
