document.addEventListener("DOMContentLoaded", () => {
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

    const addressLine1 = document.getElementById("addressLine1").value.trim();
    const addressLine2 = document.getElementById("addressLine2").value.trim();
    const city = document.getElementById("city").value;
    const province = document.getElementById("province").value;
    const postalCode = document.getElementById("postalCode").value.trim();
    const activeOption = document.querySelector(".delivery-option.active");
    const dropOff = activeOption ? activeOption.dataset.option === "drop_off" : true;

    if (!addressLine1) return showError("Street address is required.");
    if (!city) return showError("Please select a city.");
    if (!postalCode) return showError("Postal code is required.");

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
        }),
      });

      const data = await response.json();

      if (response.ok && data.status === "success") {
        document.getElementById("success-f2f-id").textContent = data.f2fOrderId || "—";
        document.getElementById("success-shipping-id").textContent = data.shippingId || "—";
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
