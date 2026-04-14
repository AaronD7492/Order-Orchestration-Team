document.addEventListener("DOMContentLoaded", () => {
  // ── Cart state (initialized from server-side data) ──
  let cart = (window.__CART__ || []).map(item => ({ ...item }));

  const summaryItems = document.getElementById("summaryItems");

  function renderCart() {
    summaryItems.innerHTML = "";

    if (cart.length === 0) {
      summaryItems.innerHTML =
        '<div style="padding:18px 16px; color:#6b7280; font-size:13px; text-align:center;">Your cart is empty.</div>';
      return;
    }

    cart.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "summary-item";
      row.innerHTML = `
        <div class="summary-item-info">
          <div class="summary-item-name">${item.productName || item.productId}</div>
          <div class="summary-item-qty">${item.quantity} ${item.unit || ""}</div>
        </div>
        <div class="item-qty-control">
          <button class="item-qty-btn remove" data-idx="${idx}" data-action="dec" title="Decrease">−</button>
          <span class="item-qty-display">${item.quantity}</span>
          <button class="item-qty-btn" data-idx="${idx}" data-action="inc" title="Increase">+</button>
        </div>
      `;
      summaryItems.appendChild(row);
    });

    // Bind +/- buttons
    summaryItems.querySelectorAll(".item-qty-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.idx, 10);
        const action = btn.dataset.action;
        const step = 0.5;

        if (action === "inc") {
          cart[idx].quantity = Math.round((cart[idx].quantity + step) * 10) / 10;
        } else {
          cart[idx].quantity = Math.round((cart[idx].quantity - step) * 10) / 10;
          if (cart[idx].quantity <= 0) {
            cart.splice(idx, 1);
          }
        }
        renderCart();
      });
    });
  }

  renderCart();

  // ── Delivery preference toggle ──────────────────────
  const options = document.querySelectorAll(".delivery-option");

  options.forEach(opt => {
    opt.addEventListener("click", () => {
      options.forEach(o => o.classList.remove("active"));
      opt.classList.add("active");
    });
  });

  // ── Place order ─────────────────────────────────────
  const btn = document.getElementById("orderBtn");
  const btnText = document.getElementById("btn-text");
  const btnSpinner = document.getElementById("btn-spinner");
  const errorAlert = document.getElementById("error-alert");
  const errorMessage = document.getElementById("error-message");
  const successModal = document.getElementById("successModal");

  function showError(msg) {
    errorMessage.textContent = msg;
    errorAlert.classList.remove("d-none");
    errorAlert.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function hideError() {
    errorAlert.classList.add("d-none");
  }

  function setLoading(loading) {
    btn.disabled = loading;
    btnText.classList.toggle("d-none", loading);
    btnSpinner.classList.toggle("d-none", !loading);
  }

  btn.addEventListener("click", async () => {
    hideError();

    if (cart.length === 0) return showError("Your cart is empty. Please go back and add items.");

    const addressLine1 = document.getElementById("addressLine1").value.trim();
    const addressLine2El = document.getElementById("addressLine2");
    const addressLine2 = addressLine2El ? addressLine2El.value.trim() : "";
    const cityEl = document.getElementById("city");
    const city = cityEl ? cityEl.value.trim() : "";
    const provinceEl = document.getElementById("province");
    const province = provinceEl ? provinceEl.value.trim() : "ON";
    const postalCodeEl = document.getElementById("postalCode");
    const postalCode = postalCodeEl ? postalCodeEl.value.trim() : "";
    const activeOption = document.querySelector(".delivery-option.active");
    const dropOff = activeOption ? activeOption.dataset.option === "drop_off" : true;

    if (!addressLine1) return showError("Street address is required.");
    if (!city) return showError("Please select a city.");

    setLoading(true);

    try {
      const response = await fetch("/checkout/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          addressLine1,
          addressLine2,
          city,
          province,
          postalCode,
          dropOff,
          items: cart,
        }),
      });

      const data = await response.json();

      if (response.ok && data.status === "success") {
        document.getElementById("success-f2f-id").textContent = data.f2fOrderId || "—";
        document.getElementById("success-shipping-id").textContent = data.shippingId || "—";
        if (data.deliveryDashboardUrl) {
          document.getElementById("de-dashboard-link").href = data.deliveryDashboardUrl;
        }
        successModal.classList.add("active");
      } else {
        const msg = data.message || data.error || "Something went wrong. Please try again.";
        if (data.error === "out_of_stock") {
          showError("One or more items are out of stock. Please update your cart and try again.");
        } else {
          showError(msg);
        }
      }
    } catch (err) {
      console.error(err);
      showError("Network error. Please check your connection and try again.");
    } finally {
      setLoading(false);
    }
  });
});
