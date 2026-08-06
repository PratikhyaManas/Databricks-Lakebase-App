/**
 * Lightweight, dependency-free live refresh for the Orders Dashboard.
 * Polls /api/orders and /api/notes on an interval and re-renders just the
 * relevant table bodies, so the page never does a jarring full reload.
 */
(function () {
  const REFRESH_MS = 15000;

  const ordersBody = document.getElementById("orders-body");
  const notesList = document.getElementById("notes-list");
  const searchInput = document.getElementById("order-search");
  const statusDot = document.getElementById("live-status");

  let currentSearch = (searchInput && searchInput.value) || "";
  let currentPage = parseInt((ordersBody && ordersBody.dataset.page) || "1", 10) || 1;
  let debounceTimer = null;

  function fmtMoney(n) {
    return "$" + Number(n).toFixed(2);
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleString();
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  async function fetchJson(path, queryParams) {
    const url = new URL(path, window.location.origin);
    if (queryParams) {
      Object.entries(queryParams).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          url.searchParams.set(key, value);
        }
      });
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error("bad status " + res.status);
    return res.json();
  }

  async function refreshOrders() {
    if (!ordersBody) return true;
    try {
      const data = await fetchJson("/api/orders", { q: currentSearch, page: currentPage });
      if (!data.items.length) {
        ordersBody.innerHTML = '<tr><td colspan="7" class="empty">No matching orders.</td></tr>';
        return true;
      }
      ordersBody.innerHTML = data.items
        .map(
          (o) => `
        <tr>
          <td>${o.order_id}</td>
          <td>${escapeHtml(o.customer || "")}</td>
          <td>${escapeHtml(o.item || "")}</td>
          <td>${o.quantity}</td>
          <td>${fmtMoney(o.amount)}</td>
          <td><span class="badge badge-${escapeHtml(o.status || "")}">${escapeHtml(o.status || "")}</span></td>
          <td>${fmtDate(o.ordered_at)}</td>
        </tr>`
        )
        .join("");
      return true;
    } catch (e) {
      console.warn("orders refresh failed:", e);
      return false;
    }
  }

  async function refreshNotes() {
    if (!notesList) return true;
    try {
      const data = await fetchJson("/api/notes");
      if (!data.items.length) {
        notesList.innerHTML = '<li class="empty">No notes yet — add one above.</li>';
        return true;
      }
      notesList.innerHTML = data.items
        .map(
          (n) => `
        <li data-id="${n.id}">
          <span>${escapeHtml(n.content)}</span>
          <span class="meta">
            ${fmtDate(n.created_at)}
            <form action="/notes/${n.id}/delete" method="post" class="inline-form">
              <input type="hidden" name="csrf_token" value="${window.__csrfToken || ""}">
              <button type="submit" class="link-btn">delete</button>
            </form>
          </span>
        </li>`
        )
        .join("");
      return true;
    } catch (e) {
      console.warn("notes refresh failed:", e);
      return false;
    }
  }

  function setLive(ok) {
    if (!statusDot) return;
    statusDot.classList.toggle("live-ok", ok);
    statusDot.classList.toggle("live-bad", !ok);
    statusDot.title = ok ? "Live — last refresh succeeded" : "Refresh failed, retrying...";
  }

  async function refreshAll() {
    const [ordersOk, notesOk] = await Promise.all([refreshOrders(), refreshNotes()]);
    setLive(ordersOk && notesOk);
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        currentSearch = searchInput.value.trim();
        currentPage = 1;
        refreshOrders();
      }, 300);
    });
  }

  setInterval(refreshAll, REFRESH_MS);
})();
