// ── Cart state ──────────────────────────────────────────────────────────────
let cart = [];

// ── Cart panel open/close ───────────────────────────────────────────────────
function openCart() {
  document.getElementById("cartPanel").classList.add("open");
  document.getElementById("cartOverlay").classList.add("open");
}

function closeCart() {
  document.getElementById("cartPanel").classList.remove("open");
  document.getElementById("cartOverlay").classList.remove("open");
}

// Wire up the cart icon in the header (loaded dynamically by components.js)
document.addEventListener("DOMContentLoaded", () => {
  // Retry a few times since header loads asynchronously
  let attempts = 0;
  const interval = setInterval(() => {
    const cartBtn = document.querySelector(".icon-btn[title='Cart']");
    if (cartBtn) {
      cartBtn.addEventListener("click", openCart);
      clearInterval(interval);
    }
    if (++attempts > 20) clearInterval(interval);
  }, 100);
});

// ── Category filter ─────────────────────────────────────────────────────────
function filterCategory(category, linkEl) {
  // Update active link
  document.querySelectorAll("#categoryList a").forEach(a => a.classList.remove("active"));
  linkEl.classList.add("active");

  // Filter visible product cards
  const activeTab = document.querySelector(".product-section.active");
  if (!activeTab) return;
  activeTab.querySelectorAll(".product-card").forEach(card => {
    const match = category === "all" || card.dataset.category === category;
    card.style.display = match ? "" : "none";
  });

  return false;
}

// ── Tab switching ───────────────────────────────────────────────────────────
function switchTab(tabId, btnEl) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".product-section").forEach(s => s.classList.remove("active"));
  btnEl.classList.add("active");
  document.getElementById(`tab-${tabId}`).classList.add("active");
}

// ── Quantity controls ───────────────────────────────────────────────────────
function adjustQty(btn, delta) {
  const input = btn.parentElement.querySelector(".qty-input");
  const step = parseFloat(input.step) || 0.5;
  const min  = parseFloat(input.min)  || 0.1;
  const max  = parseFloat(input.max)  || 9999;
  const current = parseFloat(input.value) || 1;
  const next = Math.max(min, Math.min(max, parseFloat((current + delta * step).toFixed(2))));
  input.value = next;
}

// ── Add to cart ─────────────────────────────────────────────────────────────
function addToCart(btn) {
  const card = btn.closest(".product-card");
  const productId   = card.dataset.productId;
  const productName = card.dataset.productName;
  const unit        = card.dataset.unit;
  const qty         = parseFloat(card.querySelector(".qty-input").value) || 1;

  const category = card.dataset.category || "";   // "Produce" | "Dairy" | "Meat"

  const existing = cart.find(i => i.productId === productId);
  if (existing) {
    existing.quantity = parseFloat((existing.quantity + qty).toFixed(2));
  } else {
    cart.push({ productId, productName, quantity: qty, unit, category });
  }

  renderCart();
  openCart();
}

// ── Remove from cart ────────────────────────────────────────────────────────
function removeFromCart(productId) {
  cart = cart.filter(i => i.productId !== productId);
  renderCart();
}

// ── Render cart panel ───────────────────────────────────────────────────────
function renderCart() {
  const list = document.getElementById("cartItemsList");
  const btn  = document.getElementById("checkoutBtn");

  if (cart.length === 0) {
    list.innerHTML = '<p class="cart-empty">Your cart is empty.</p>';
    btn.disabled = true;
    updateCartBadge();
    return;
  }

  list.innerHTML = cart.map(item => `
    <div class="cart-item">
      <div class="cart-item-info">
        <div class="cart-item-name">${item.productName}</div>
        <div class="cart-item-qty">${item.quantity} ${item.unit}</div>
      </div>
      <button class="cart-item-remove" onclick="removeFromCart('${item.productId}')" title="Remove">✕</button>
    </div>
  `).join("");

  btn.disabled = false;
  updateCartBadge();
}

// ── Cart badge in header ────────────────────────────────────────────────────
function updateCartBadge() {
  const badge = document.querySelector(".cart-badge");
  if (!badge) return;
  const total = cart.reduce((sum, i) => sum + i.quantity, 0);
  badge.textContent = total > 0 ? Math.round(total) : "0";
}

// ── Go to checkout ──────────────────────────────────────────────────────────
async function goToCheckout() {
  if (cart.length === 0) return;

  const btn = document.getElementById("checkoutBtn");
  btn.disabled = true;
  btn.textContent = "Loading...";

  try {
    const resp = await fetch("/checkout/initiate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items: cart,
        userToken: null,   // C&S JWT token — set when auth is integrated
      }),
    });

    const data = await resp.json();

    if (resp.ok && data.redirect_url) {
      window.location.href = data.redirect_url;
    } else {
      alert(data.error || "Could not start checkout. Please try again.");
      btn.disabled = false;
      btn.textContent = "Go to Checkout";
    }
  } catch (err) {
    console.error(err);
    alert("Network error. Please check your connection.");
    btn.disabled = false;
    btn.textContent = "Go to Checkout";
  }
}
