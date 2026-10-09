const form = document.querySelector("#search-form");
const searchButton = form.querySelector(".search-button");
const searchButtonText = searchButton.querySelector("span");
const formError = document.querySelector("#form-error");
const resultsSection = document.querySelector("#results-section");
const resultsSummary = document.querySelector("#results-summary");
const resultList = document.querySelector("#result-list");
const exportButton = document.querySelector("#export-button");
const childrenInput = document.querySelector("#children");
const childrenAges = document.querySelector("#children-ages");
const childrenAgesField = document.querySelector("#children-ages-field");
let currentExportUrl = "";

const currencyFormatters = new Map();

function formatPrice(amount, currency) {
  if (!currencyFormatters.has(currency)) {
    currencyFormatters.set(currency, new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }));
  }
  return currencyFormatters.get(currency).format(amount);
}

function safeExternalUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function createIcon(path) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("fill", "none");
  const element = document.createElementNS("http://www.w3.org/2000/svg", "path");
  element.setAttribute("d", path);
  element.setAttribute("stroke", "currentColor");
  element.setAttribute("stroke-width", "1.8");
  element.setAttribute("stroke-linecap", "round");
  element.setAttribute("stroke-linejoin", "round");
  svg.append(element);
  return svg;
}

function renderOffers(data) {
  resultList.replaceChildren();
  if (data.offers.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("strong");
    title.textContent = "Nothing on the shortlist just yet.";
    const message = document.createElement("span");
    message.textContent = "Try a wider budget or a lower minimum rating to see more stays.";
    empty.append(title, message);
    resultList.append(empty);
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "result-table-wrap";
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", "Hotel search results");
  wrapper.tabIndex = 0;

  const table = document.createElement("table");
  table.className = "result-table";
  const header = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const label of ["Accommodation", "Per night", `Total · ${data.nights} nights`, "GPS location", "Availability"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    headerRow.append(cell);
  }
  header.append(headerRow);

  const body = document.createElement("tbody");
  data.offers.forEach((offer, index) => {
    const row = document.createElement("tr");
    const accommodation = document.createElement("th");
    accommodation.scope = "row";
    const name = document.createElement("span");
    name.className = "table-hotel-name";
    name.textContent = offer.hotel_name;
    accommodation.append(name);

    const details = [offer.room_name, offer.address];
    if (offer.guest_rating > 0) details.push(`${offer.guest_rating.toFixed(1)} guest rating`);
    for (const detail of details) {
      if (!detail) continue;
      const line = document.createElement("span");
      line.className = "table-hotel-detail";
      line.textContent = detail;
      accommodation.append(line);
    }

    const nightly = document.createElement("td");
    nightly.textContent = formatPrice(offer.nightly_price, offer.currency);
    const total = document.createElement("td");
    total.textContent = formatPrice(offer.total_price, offer.currency);

    const location = document.createElement("td");
    if (offer.latitude !== null && offer.longitude !== null) {
      const coordinates = document.createElement("span");
      coordinates.className = "table-hotel-detail";
      coordinates.textContent = `${offer.latitude}, ${offer.longitude}`;
      location.append(coordinates);
    }
    const mapQuery = offer.latitude !== null && offer.longitude !== null
      ? `${offer.latitude},${offer.longitude}`
      : [offer.hotel_name, offer.address].filter(Boolean).join(", ");
    if (mapQuery) {
      const mapLink = document.createElement("a");
      mapLink.className = "table-link";
      mapLink.href = `https://www.google.com/maps?q=${encodeURIComponent(mapQuery)}`;
      mapLink.target = "_blank";
      mapLink.rel = "noopener noreferrer";
      mapLink.textContent = offer.latitude !== null && offer.longitude !== null ? "View GPS map" : "Find on map";
      location.append(mapLink);
    } else {
      location.textContent = "Not available";
    }

    const availability = document.createElement("td");
    const externalStayUrl = safeExternalUrl(offer.deep_link);
    if (externalStayUrl) {
      const link = document.createElement("a");
      link.className = "table-link";
      link.href = externalStayUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Check stay";
      availability.append(link);
    } else {
      availability.textContent = "—";
    }

    row.append(accommodation, nightly, total, location, availability);
    body.append(row);
  });

  table.append(header, body);
  wrapper.append(table);
  resultList.append(wrapper);
}

function updateChildrenAges(count, initialAges = []) {
  childrenAges.replaceChildren();
  childrenAgesField.hidden = count === 0;
  for (let index = 0; index < count; index += 1) {
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "17";
    input.required = true;
    input.setAttribute("aria-label", `Age of child ${index + 1}`);
    input.placeholder = `Age ${index + 1}`;
    input.value = initialAges[index] ?? "";
    childrenAges.append(input);
  }
}

function readSearchForm() {
  const values = new FormData(form);
  const childCount = Number(values.get("children") || 0);
  const ages = [...childrenAges.querySelectorAll("input")].map((input) => Number(input.value));
  return {
    destination: String(values.get("destination")).trim(),
    check_in: values.get("check_in"),
    check_out: values.get("check_out"),
    adults: Number(values.get("adults")),
    children_ages: childCount > 0 ? ages : [],
    rooms: Number(values.get("rooms")),
    currency: values.get("currency"),
    min_price: values.get("min_price") ? Number(values.get("min_price")) : null,
    max_price: values.get("max_price") ? Number(values.get("max_price")) : null,
    min_rating: values.get("min_rating") ? Number(values.get("min_rating")) : null,
  };
}

function showError(message) {
  formError.textContent = message;
  formError.hidden = false;
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("Could not load your saved search settings.");
    const config = await response.json();
    const settings = config.search;
    document.querySelector("#destination").value = settings.destination;
    document.querySelector("#check-in").value = settings.check_in;
    document.querySelector("#check-out").value = settings.check_out;
    document.querySelector("#adults").value = settings.adults;
    document.querySelector("#rooms").value = settings.rooms;
    document.querySelector("#currency").value = settings.currency;
    document.querySelector("#min-price").value = settings.min_price ?? "";
    document.querySelector("#max-price").value = settings.max_price ?? "";
    document.querySelector("#min-rating").value = settings.min_rating ?? "";
    document.querySelector("#children").value = settings.children_ages.length;
    updateChildrenAges(settings.children_ages.length, settings.children_ages);
    document.querySelector("#provider-label").textContent = config.provider;
  } catch (error) {
    showError(error instanceof Error ? error.message : "Could not load your saved search settings.");
  }
}

childrenInput.addEventListener("input", () => {
  const count = Math.min(10, Math.max(0, Number(childrenInput.value) || 0));
  updateChildrenAges(count);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.hidden = true;
  const search = readSearchForm();
  if (search.check_out <= search.check_in) {
    showError("Choose a check-out date after your check-in date.");
    document.querySelector("#check-out").focus();
    return;
  }
  if (search.min_price !== null && search.max_price !== null && search.min_price > search.max_price) {
    showError("Your maximum nightly budget should be higher than the minimum.");
    document.querySelector("#max-price").focus();
    return;
  }

  searchButton.disabled = true;
  searchButtonText.textContent = "Finding your stay…";
  exportButton.hidden = true;
  currentExportUrl = "";
  resultsSection.hidden = false;
  resultsSection.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    block: "start",
  });
  resultsSummary.textContent = "Searching the places that fit your trip.";
  resultList.innerHTML = '<div class="loading-state" aria-label="Searching"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>';

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(search),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Your search could not be completed. Please try again.");
    renderOffers(data);
    resultsSummary.textContent = `${data.count} ${data.count === 1 ? "stay" : "stays"} for ${data.destination} · ${data.nights} ${data.nights === 1 ? "night" : "nights"}`;
    currentExportUrl = `/api/searches/${encodeURIComponent(data.search_id)}/export`;
    exportButton.hidden = data.count === 0;
    document.querySelector("#welcome-note").hidden = true;
  } catch (error) {
    resultList.replaceChildren();
    resultsSummary.textContent = "";
    const message = error instanceof Error ? error.message : "Your search could not be completed. Please try again.";
    const errorState = document.createElement("div");
    errorState.className = "empty-state";
    errorState.setAttribute("role", "alert");
    const title = document.createElement("strong");
    title.textContent = "We couldn't complete that search.";
    const explanation = document.createElement("span");
    explanation.textContent = message;
    errorState.append(title, explanation);
    resultList.append(errorState);
  } finally {
    searchButton.disabled = false;
    searchButtonText.textContent = "Find my stay";
  }
});

exportButton.addEventListener("click", async () => {
  if (!currentExportUrl) return;
  exportButton.disabled = true;
  const label = exportButton.querySelector("span");
  label.textContent = "Preparing…";
  try {
    const response = await fetch(currentExportUrl);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Your shortlist could not be exported.");
    }
    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `stays-${document.querySelector("#check-in").value}.xlsx`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
  } catch (error) {
    showError(error instanceof Error ? error.message : "Your shortlist could not be exported.");
  } finally {
    exportButton.disabled = false;
    label.textContent = "Save shortlist";
  }
});

loadConfig();
