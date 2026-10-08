(() => {
  const page = document.querySelector("[data-results-page]");
  if (!page) return;

  const resultId = page.dataset.searchId;
  const loading = document.querySelector("#results-loading");
  const unavailable = document.querySelector("#results-unavailable");
  const unavailableMessage = document.querySelector("#unavailable-message");
  const content = document.querySelector("#results-content");
  const exportButton = document.querySelector("#export-button");
  const exportButtonLabel = document.querySelector("#export-button-label");
  const exportStatus = document.querySelector("#export-status");
  const RESULT_TTL_MS = 30 * 60 * 1000;
  let isExporting = false;
  let resultPayload;

  function showUnavailable(message) {
    loading.hidden = true;
    content.hidden = true;
    unavailable.hidden = false;
    unavailableMessage.textContent = message;
  }

  function formatDate(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "Date unavailable";
    const [year, month, day] = value.split("-").map(Number);
    const parsed = new Date(year, month - 1, day, 12);
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(parsed);
  }

  function countNights(checkIn, checkOut) {
    const start = Date.parse(`${checkIn}T00:00:00Z`);
    const end = Date.parse(`${checkOut}T00:00:00Z`);
    return Number.isFinite(start) && Number.isFinite(end) && end > start
      ? Math.round((end - start) / 86_400_000)
      : 0;
  }

  function formatCurrency(value, currency) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "—";
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency,
        maximumFractionDigits: 2,
      }).format(amount);
    } catch {
      return `${currency} ${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    }
  }

  function addTextCell(row, value, className = "") {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = value;
    row.append(cell);
    return cell;
  }

  function makeOfferRow(offer, index) {
    const row = document.createElement("tr");
    const rowNumber = document.createElement("th");
    rowNumber.className = "sheet-row-number";
    rowNumber.scope = "row";
    rowNumber.textContent = String(index + 1);
    row.append(rowNumber);

    const accommodation = document.createElement("td");
    accommodation.className = "sheet-accommodation";
    const name = document.createElement("strong");
    name.textContent = typeof offer.hotel_name === "string" ? offer.hotel_name : "Unnamed accommodation";
    accommodation.append(name);
    if (typeof offer.address === "string" && offer.address.trim()) {
      const address = document.createElement("span");
      address.textContent = offer.address;
      accommodation.append(address);
    }
    row.append(accommodation);

    addTextCell(row, typeof offer.room_name === "string" && offer.room_name.trim()
      ? offer.room_name
      : "Room details not listed");
    addTextCell(row, formatCurrency(offer.nightly_price, offer.currency));
    addTextCell(row, formatCurrency(offer.total_price, offer.currency));

    const rating = Number(offer.guest_rating);
    addTextCell(row, offer.guest_rating !== null && Number.isFinite(rating)
      ? `${rating.toFixed(1)} / 10`
      : "Unrated");

    const listingCell = document.createElement("td");
    if (typeof offer.deep_link === "string") {
      try {
        const listingUrl = new URL(offer.deep_link);
        if (["http:", "https:"].includes(listingUrl.protocol) && !listingUrl.username && !listingUrl.password) {
          const link = document.createElement("a");
          link.className = "spreadsheet-link";
          link.href = listingUrl.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = "Open listing";
          listingCell.append(link);
        }
      } catch {
        // Invalid provider links are shown as unavailable instead of being navigated to.
      }
    }
    if (!listingCell.childElementCount) {
      listingCell.textContent = "Not provided";
      listingCell.className = "sheet-muted";
    }
    row.append(listingCell);
    return row;
  }

  function renderResults(data) {
    const search = data.search;
    const offers = data.offers;
    const nights = countNights(search.check_in, search.check_out);
    const currency = typeof search.currency === "string" ? search.currency : "GHS";

    document.querySelector("#summary-destination").textContent = search.destination;
    document.querySelector("#summary-dates").textContent = `${formatDate(search.check_in)} – ${formatDate(search.check_out)} · ${nights} ${nights === 1 ? "night" : "nights"}`;
    const adults = Number(search.adults) || 0;
    const children = Array.isArray(search.children_ages) ? search.children_ages.length : 0;
    const rooms = Number(search.rooms) || 0;
    document.querySelector("#summary-guests").textContent = [
      `${adults} ${adults === 1 ? "adult" : "adults"}`,
      children ? `${children} ${children === 1 ? "child" : "children"}` : null,
      `${rooms} ${rooms === 1 ? "room" : "rooms"}`,
    ].filter(Boolean).join(" · ");

    document.querySelector("#result-count").textContent = String(offers.length);
    const providerNotice = document.querySelector("#provider-notice");
    providerNotice.textContent = data.is_sample
      ? "Sample results from the local demo provider. These are not live prices or availability."
      : `Results from ${typeof data.provider === "string" ? data.provider : "Booking.com"}. Prices and availability can change; confirm details with the provider.`;

    document.querySelector("#spreadsheet-footnote").textContent =
      `Prices are shown in ${currency}. Nightly rates are averages across ${nights} ${nights === 1 ? "night" : "nights"}; confirm final prices and availability with the listing provider.`;

    const rows = document.querySelector("#results-rows");
    rows.replaceChildren(...offers.map(makeOfferRow));
    document.querySelector("#no-matches").hidden = offers.length !== 0;
    document.querySelector("#spreadsheet-shell").hidden = offers.length === 0;
    exportButton.hidden = offers.length === 0;
    content.hidden = false;
    loading.hidden = true;
  }

  async function downloadWorkbook() {
    if (isExporting || !resultPayload) return;
    isExporting = true;
    exportButton.disabled = true;
    exportButton.setAttribute("aria-busy", "true");
    exportButtonLabel.textContent = "Preparing Excel…";
    exportStatus.hidden = false;
    exportStatus.textContent = "Creating your Excel workbook…";
    exportStatus.classList.remove("is-error");

    try {
      const response = await fetch(page.dataset.exportUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify(resultPayload),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || "The Excel workbook could not be created. Try downloading again.");
      }

      const workbook = await response.blob();
      if (!workbook.size) throw new Error("The Excel workbook was empty. Try downloading again.");
      const objectUrl = URL.createObjectURL(workbook);
      const download = document.createElement("a");
      download.href = objectUrl;
      download.download = "hotel-search-results.xlsx";
      document.body.append(download);
      download.click();
      download.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      exportStatus.textContent = "Your Excel workbook is ready. It should appear in your downloads.";
    } catch (error) {
      exportStatus.textContent = error instanceof Error
        ? error.message
        : "The Excel workbook could not be created. Try downloading again.";
      exportStatus.classList.add("is-error");
    } finally {
      isExporting = false;
      exportButton.disabled = false;
      exportButton.removeAttribute("aria-busy");
      exportButtonLabel.textContent = "Download Excel";
    }
  }

  if (page.dataset.searchValid !== "true") {
    showUnavailable("This results link is invalid. Run a new search to create a fresh Excel report.");
    return;
  }

  try {
    const storedResult = sessionStorage.getItem(`hotel-search-results:${resultId}`);
    resultPayload = storedResult ? JSON.parse(storedResult) : null;
  } catch {
    showUnavailable("Your browser could not open these results. Enable session storage and run the search again.");
    return;
  }

  const createdAt = resultPayload?.created_at_ms;
  const age = Date.now() - createdAt;
  if (
    !resultPayload ||
    resultPayload.search_id !== resultId ||
    !Number.isInteger(createdAt) ||
    age < -60_000 ||
    age > RESULT_TTL_MS ||
    !resultPayload.search ||
    typeof resultPayload.search.destination !== "string" ||
    !Array.isArray(resultPayload.offers)
  ) {
    showUnavailable("These results are no longer available in this browser tab. Run a new search to create a fresh Excel report.");
    return;
  }

  try {
    renderResults(resultPayload);
  } catch {
    showUnavailable("These results could not be displayed. Run the search again to create a fresh Excel report.");
    return;
  }

  exportButton.addEventListener("click", downloadWorkbook);
  if (resultPayload.auto_download === true && resultPayload.offers.length > 0) {
    window.setTimeout(() => void downloadWorkbook(), 150);
  }
})();
