const form = document.querySelector("#search-form");
const searchButton = document.querySelector("#search-button");
const searchButtonLabel = document.querySelector("#search-button-label");
const searchError = document.querySelector("#search-error");
const searchStatus = document.querySelector("#search-status");

function localToday() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function readChildrenAges() {
  const value = form.elements.children_ages.value.trim();
  if (!value) return [];

  const parts = value.split(",").map((part) => part.trim());
  if (parts.length > 8 || parts.some((part) => !/^\d{1,2}$/.test(part))) {
    throw new Error("Enter up to 8 children’s ages as whole numbers from 0 to 17, separated by commas.");
  }

  const ages = parts.map(Number);
  if (ages.some((age) => age < 0 || age > 17)) {
    throw new Error("Children’s ages must be between 0 and 17.");
  }
  return ages;
}

function validateDates(checkIn, checkOut) {
  if (checkIn < localToday()) {
    throw new Error("Check-in must be today or a future date.");
  }
  if (checkOut <= checkIn) {
    throw new Error("Check-out must be after check-in.");
  }
  const nights = (Date.parse(`${checkOut}T00:00:00Z`) - Date.parse(`${checkIn}T00:00:00Z`)) / 86400000;
  if (nights > 365) {
    throw new Error("A stay cannot be longer than 365 nights.");
  }
}

function showError(message, control) {
  searchError.textContent = message;
  if (control) control.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  searchError.textContent = "";
  searchStatus.hidden = true;
  searchStatus.classList.remove("is-loading");

  let childrenAges;
  try {
    childrenAges = readChildrenAges();
  } catch (error) {
    showError(error.message, form.elements.children_ages);
    return;
  }

  const checkIn = form.elements.check_in.value;
  const checkOut = form.elements.check_out.value;
  try {
    validateDates(checkIn, checkOut);
  } catch (error) {
    showError(error.message, checkOut <= checkIn ? form.elements.check_out : form.elements.check_in);
    return;
  }

  const minPrice = form.elements.min_price.value;
  const maxPrice = form.elements.max_price.value;
  if (minPrice && maxPrice && Number(minPrice) > Number(maxPrice)) {
    showError("Minimum price must not be greater than maximum price.", form.elements.min_price);
    return;
  }

  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }

  const payload = {
    destination: form.elements.destination.value.trim(),
    check_in: checkIn,
    check_out: checkOut,
    adults: Number(form.elements.adults.value),
    children_ages: childrenAges,
    rooms: Number(form.elements.rooms.value),
    currency: form.elements.currency.value,
    min_price: minPrice || null,
    max_price: maxPrice || null,
    min_rating: form.elements.min_rating.value || null,
  };

  searchButton.disabled = true;
  searchButton.setAttribute("aria-busy", "true");
  searchButtonLabel.textContent = "Searching…";
  searchStatus.textContent = "Searching stays with your dates and preferences…";
  searchStatus.classList.add("is-loading");
  searchStatus.hidden = false;

  try {
    const response = await fetch(form.dataset.searchUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The search could not be completed. Please try again.");
    if (
      typeof data.search_id !== "string" ||
      !/^[A-Za-z0-9_-]{20,64}$/.test(data.search_id) ||
      !Array.isArray(data.offers) ||
      !data.search ||
      typeof data.search !== "object"
    ) {
      throw new Error("The search returned incomplete results. Please try again.");
    }

    const resultsUrl = new URL(data.results_url, window.location.origin);
    if (
      resultsUrl.origin !== window.location.origin ||
      !resultsUrl.pathname.startsWith("/results/") ||
      !resultsUrl.pathname.endsWith(data.search_id)
    ) {
      throw new Error("Search results could not be opened. Please try again.");
    }

    try {
      sessionStorage.setItem(
        `hotel-search-results:${data.search_id}`,
        JSON.stringify({ ...data, auto_download: true }),
      );
    } catch {
      throw new Error("Your browser could not keep these results for the next page. Enable session storage and try again.");
    }

    window.location.assign(resultsUrl.pathname);
  } catch (error) {
    searchStatus.hidden = true;
    searchStatus.classList.remove("is-loading");
    showError(error.message || "Something went wrong while searching. Please try again.");
  } finally {
    searchButton.disabled = false;
    searchButton.removeAttribute("aria-busy");
    searchButtonLabel.textContent = "Find stays";
  }
});

const checkInInput = form.elements.check_in;
const checkOutInput = form.elements.check_out;
checkInInput.min = localToday();
checkOutInput.min = checkInInput.value || localToday();
checkInInput.addEventListener("change", () => {
  if (checkInInput.value) {
    checkOutInput.min = checkInInput.value;
    if (checkOutInput.value <= checkInInput.value) {
      const nextDay = new Date(`${checkInInput.value}T12:00:00`);
      nextDay.setDate(nextDay.getDate() + 1);
      checkOutInput.value = `${nextDay.getFullYear()}-${String(nextDay.getMonth() + 1).padStart(2, "0")}-${String(nextDay.getDate()).padStart(2, "0")}`;
    }
  } else {
    checkOutInput.min = localToday();
  }
});
