// ── Supply Network config ────────────────────────────────────────────────────
// Change this one line when deploying to the live server
const SUPPLY_API_URL = "http://165.22.230.110:5002";

// ── Category emoji map ───────────────────────────────────────────────────────
const CATEGORY_EMOJI = { Dairy: "🥛", Meat: "🥩", Produce: "🥦" };

// ── Load packages from Supply Network API ───────────────────────────────────
async function loadPackages() {
  const container = document.getElementById("packagesContainer");
  const loading   = document.getElementById("packagesLoading");

  try {
    const resp = await fetch(`${SUPPLY_API_URL}/api/inventory/packages`);
    if (!resp.ok) throw new Error(`API returned ${resp.status}`);
    const data = await resp.json();

    // Group packages by category
    const groups = {};
    data.packages.forEach(pkg => {
      if (!groups[pkg.category]) groups[pkg.category] = [];
      groups[pkg.category].push(pkg);
    });

    // Build HTML
    let html = "";
    for (const [category, packages] of Object.entries(groups)) {
      const emoji = CATEGORY_EMOJI[category] || "";
      html += `
        <div class="package-category-group" data-group-category="${category}">
          <div class="package-category-heading">${emoji} ${category}</div>
          <div class="package-cards-row">
            ${packages.map(pkg => `
              <div class="package-card"
                   data-pkg-id="${pkg.packageId}"
                   data-pkg-name="${pkg.category} Bundle — ${pkg.sizeKg} kg"
                   data-pkg-category="${pkg.category}"
                   data-pkg-size="${pkg.sizeKg}">
                <div class="package-card-header">
                  <div class="package-name">${pkg.category} Bundle</div>
                  <span class="package-size-badge">${pkg.sizeKg} kg</span>
                </div>
                <button class="package-toggle-desc" onclick="toggleDesc(this)">What's inside ▾</button>
                <div class="package-desc">
                  <ul>
                    ${pkg.contents.map(c => `<li>${c.qty} ${c.unit} ${c.item}</li>`).join("")}
                  </ul>
                </div>
                <button class="package-add-btn ${!pkg.canFulfil ? 'unavailable' : ''}"
                        onclick="addPackageToCart(this)"
                        ${!pkg.canFulfil ? 'disabled title="Not enough stock"' : ""}>
                  ${pkg.canFulfil ? "Add to Cart" : "Out of Stock"}
                </button>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    container.innerHTML = html;

  } catch (err) {
    console.warn("Supply Network unavailable, using fallback bundles:", err);
    renderFallbackPackages(container);
  }
}

// ── Fallback bundles (used when API is unreachable) ──────────────────────────
function renderFallbackPackages(container) {
  const fallback = [
    { category: "Dairy",   sizeKg: 5,  packageId: "dairy-5",
      contents: [{qty:2,unit:"kg",item:"Whole Milk"},{qty:1,unit:"kg",item:"Cheddar Cheese"},{qty:1,unit:"kg",item:"Plain Yogurt"},{qty:.5,unit:"kg",item:"Butter"},{qty:.5,unit:"kg",item:"Cream Cheese"}] },
    { category: "Dairy",   sizeKg: 10, packageId: "dairy-10",
      contents: [{qty:3,unit:"kg",item:"Whole Milk"},{qty:2,unit:"kg",item:"Cheddar Cheese"},{qty:2,unit:"kg",item:"Plain Yogurt"},{qty:1.5,unit:"kg",item:"Butter"},{qty:1,unit:"kg",item:"Cream Cheese"},{qty:.5,unit:"kg",item:"Sour Cream"}] },
    { category: "Dairy",   sizeKg: 20, packageId: "dairy-20",
      contents: [{qty:6,unit:"kg",item:"Whole Milk"},{qty:4,unit:"kg",item:"Cheddar Cheese"},{qty:4,unit:"kg",item:"Plain Yogurt"},{qty:3,unit:"kg",item:"Butter"},{qty:2,unit:"kg",item:"Cream Cheese"},{qty:1,unit:"kg",item:"Sour Cream"}] },
    { category: "Meat",    sizeKg: 5,  packageId: "meat-5",
      contents: [{qty:2,unit:"kg",item:"Ground Beef"},{qty:1.5,unit:"kg",item:"Chicken Breast"},{qty:1,unit:"kg",item:"Pork Chops"},{qty:.5,unit:"kg",item:"Beef Sausages"}] },
    { category: "Meat",    sizeKg: 10, packageId: "meat-10",
      contents: [{qty:3,unit:"kg",item:"Ground Beef"},{qty:2.5,unit:"kg",item:"Chicken Breast"},{qty:2,unit:"kg",item:"Pork Chops"},{qty:1.5,unit:"kg",item:"Beef Sausages"},{qty:1,unit:"kg",item:"Lamb Shoulder"}] },
    { category: "Meat",    sizeKg: 20, packageId: "meat-20",
      contents: [{qty:6,unit:"kg",item:"Ground Beef"},{qty:5,unit:"kg",item:"Chicken Breast"},{qty:4,unit:"kg",item:"Pork Chops"},{qty:3,unit:"kg",item:"Beef Sausages"},{qty:2,unit:"kg",item:"Lamb Shoulder"}] },
    { category: "Produce", sizeKg: 5,  packageId: "produce-5",
      contents: [{qty:1,unit:"kg",item:"Tomatoes"},{qty:1,unit:"kg",item:"Carrots"},{qty:1,unit:"kg",item:"Potatoes"},{qty:.5,unit:"kg",item:"Spinach"},{qty:.5,unit:"kg",item:"Broccoli"},{qty:.5,unit:"kg",item:"Apples"}] },
    { category: "Produce", sizeKg: 10, packageId: "produce-10",
      contents: [{qty:2,unit:"kg",item:"Tomatoes"},{qty:2,unit:"kg",item:"Carrots"},{qty:2,unit:"kg",item:"Potatoes"},{qty:1,unit:"kg",item:"Spinach"},{qty:1,unit:"kg",item:"Broccoli"},{qty:1,unit:"kg",item:"Apples"},{qty:1,unit:"kg",item:"Onions"}] },
    { category: "Produce", sizeKg: 20, packageId: "produce-20",
      contents: [{qty:4,unit:"kg",item:"Tomatoes"},{qty:4,unit:"kg",item:"Carrots"},{qty:4,unit:"kg",item:"Potatoes"},{qty:2,unit:"kg",item:"Spinach"},{qty:2,unit:"kg",item:"Broccoli"},{qty:2,unit:"kg",item:"Apples"},{qty:2,unit:"kg",item:"Onions"}] },
  ];
  // Reuse the same rendering logic by faking canFulfil: true
  const fakeData = { packages: fallback.map(p => ({ ...p, canFulfil: true })) };
  const fakeResp = { json: async () => fakeData, ok: true };
  // Just build the HTML directly
  const groups = {};
  fallback.forEach(pkg => {
    if (!groups[pkg.category]) groups[pkg.category] = [];
    groups[pkg.category].push({ ...pkg, canFulfil: true });
  });
  let html = "";
  for (const [category, packages] of Object.entries(groups)) {
    const emoji = CATEGORY_EMOJI[category] || "";
    html += `
      <div class="package-category-group" data-group-category="${category}">
        <div class="package-category-heading">${emoji} ${category}</div>
        <div class="package-cards-row">
          ${packages.map(pkg => `
            <div class="package-card"
                 data-pkg-id="${pkg.packageId}"
                 data-pkg-name="${pkg.category} Bundle — ${pkg.sizeKg} kg"
                 data-pkg-category="${pkg.category}"
                 data-pkg-size="${pkg.sizeKg}">
              <div class="package-card-header">
                <div class="package-name">${pkg.category} Bundle</div>
                <span class="package-size-badge">${pkg.sizeKg} kg</span>
              </div>
              <button class="package-toggle-desc" onclick="toggleDesc(this)">What's inside ▾</button>
              <div class="package-desc">
                <ul>${pkg.contents.map(c => `<li>${c.qty} ${c.unit} ${c.item}</li>`).join("")}</ul>
              </div>
              <button class="package-add-btn" onclick="addPackageToCart(this)">Add to Cart</button>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }
  container.innerHTML = html;
}



function toggleDesc(btn) {
  const desc = btn.nextElementSibling;
  const open = desc.classList.toggle("open");
  btn.textContent = open ? "What's inside ▴" : "What's inside ▾";
}

function addPackageToCart(btn) {
  const card = btn.closest(".package-card");
  const pkgId       = card.dataset.pkgId;
  const pkgName     = card.dataset.pkgName;
  const pkgCategory = card.dataset.pkgCategory;
  const pkgSize     = parseInt(card.dataset.pkgSize, 10);

  // Packages use a synthetic productId so order orchestration can route them
  const existing = cart.find(i => i.productId === pkgId);
  if (existing) {
    existing.quantity += 1;
  } else {
    cart.push({
      productId:   pkgId,
      productName: pkgName,
      quantity:    1,
      unit:        "package",
      category:    pkgCategory,
      isPackage:   true,
      packageSize: pkgSize,
    });
  }

  // Visual feedback on button
  btn.textContent = "✓ Added";
  btn.classList.add("added");
  setTimeout(() => {
    btn.textContent = "Add to Cart";
    btn.classList.remove("added");
  }, 1800);

  renderCart();
  showToast(`${pkgName} added to cart`, "success");
  openCart();
}

// ── Toast notification ──────────────────────────────────────────────────────
function showToast(message, type = "") {
  const toast = document.getElementById("orderToast");
  toast.textContent = message;
  toast.className = "order-toast" + (type ? " " + type : "");
  // Force reflow so transition plays
  void toast.offsetWidth;
  toast.classList.add("show");
  clearTimeout(toast._hideTimer);
  toast._hideTimer = setTimeout(() => toast.classList.remove("show"), 2800);
}

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
  // Load bundles from Supply Network API
  loadPackages();

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

  // Filter warehouse/supplier product cards
  const activeTab = document.querySelector(".product-section.active");
  if (activeTab) {
    activeTab.querySelectorAll(".product-card").forEach(card => {
      const match = category === "all" || card.dataset.category === category;
      card.style.display = match ? "" : "none";
    });
  }

  // Filter package category groups
  document.querySelectorAll(".package-category-group").forEach(group => {
    const match = category === "all" || group.dataset.groupCategory === category;
    group.style.display = match ? "" : "none";
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
        <div class="cart-item-qty">${item.isPackage ? `${item.quantity} × ${item.packageSize} kg package` : `${item.quantity} ${item.unit}`}</div>
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