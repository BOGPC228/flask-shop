let products = [];
let categories = [];
let storeSettings = {
    store_name: "TechStore",
    hero_title: "Каталог товаров",
    hero_subtitle: "Актуальные гаджеты с быстрой доставкой",
    contact_info: "",
    delivery_cost: "0"
};
let activeCategoryId = null;
let searchQuery = "";
let appliedPromo = null; // { code, discount_percent }

let cart = [];
try {
    cart = JSON.parse(localStorage.getItem("shop_cart")) || [];
} catch {
    cart = [];
}
let currentUser = null;
let isRegisterMode = false;

function saveCart() {
    localStorage.setItem("shop_cart", JSON.stringify(cart));
}

// --- Загрузка данных при старте ---
document.addEventListener("DOMContentLoaded", async () => {
    await loadSettings();
    await checkAuth();
    await loadCategories();
    await loadProducts();
    setupEvents();
});

async function loadSettings() {
    const res = await fetch("/api/settings");
    if (!res.ok) return;
    storeSettings = await res.json();
    applyStoreSettingsUI();
}

function applyStoreSettingsUI() {
    const name = storeSettings.store_name || "TechStore";
    document.title = `${name} — Магазин`;
    document.getElementById("storeLogo").textContent = name;
    document.getElementById("heroTitle").textContent = storeSettings.hero_title || "Каталог товаров";
    document.getElementById("heroSubtitle").textContent = storeSettings.hero_subtitle || "";
    document.getElementById("footerContact").textContent = storeSettings.contact_info || "";
    updateCartUI();
}

async function checkAuth() {
    const res = await fetch("/api/me");
    const data = await res.json();
    currentUser = data.logged_in ? data : null;
    renderAuthUI();
}

async function loadCategories() {
    const res = await fetch("/api/categories");
    if (!res.ok) return;
    categories = await res.json();
    renderCategoryFilters();
    renderCategorySelect();
    renderAdminCategories();
}

async function loadProducts() {
    const res = await fetch("/api/products");
    products = await res.json();

    // Актуализируем сохраненную корзину с учетом наличия
    cart = cart
        .map(item => products.find(p => p.id === item.id))
        .filter(p => p && p.stock > 0);
    saveCart();
    updateCartUI();

    renderProducts();
    renderAdminList();
}

// --- Отрисовка шапки и прав ---
function renderAuthUI() {
    const authArea = document.getElementById("authArea");
    const adminBtn = document.getElementById("adminBtn");
    const adminOnlyTabs = [
        "statsTabBtn",
        "categoriesTabBtn",
        "promosTabBtn",
        "usersTabBtn",
        "logsTabBtn",
        "settingsTabBtn"
    ];

    if (currentUser) {
        authArea.innerHTML = `
            <span class="user-badge">${currentUser.username}</span>
            <button id="myOrdersBtn" class="btn btn-secondary btn-sm">Мои заказы</button>
            <button id="logoutBtn" class="btn btn-secondary btn-sm">Выйти</button>
        `;
        document.getElementById("myOrdersBtn").onclick = () => {
            loadMyOrders();
            openModal("profileModal");
        };
        document.getElementById("logoutBtn").onclick = logout;

        const hasPanelAccess = currentUser.role === "admin" || currentUser.role === "manager";
        const isAdmin = currentUser.role === "admin";

        adminBtn.classList.toggle("hidden", !hasPanelAccess);
        const panelName = currentUser.role === "manager" ? "Кабинет менеджера" : "Админ-панель";
        adminBtn.textContent = panelName;
        document.getElementById("adminModalTitle").textContent = panelName;

        adminOnlyTabs.forEach(id => {
            document.getElementById(id).classList.toggle("hidden", !isAdmin);
        });
    } else {
        authArea.innerHTML = `<button id="loginOpenBtn" class="btn btn-primary">Войти</button>`;
        document.getElementById("loginOpenBtn").onclick = () => openModal("authModal");
        adminBtn.classList.add("hidden");
        adminOnlyTabs.forEach(id => document.getElementById(id).classList.add("hidden"));
    }
}

// --- Каталог и фильтры ---
function renderCategoryFilters() {
    const bar = document.getElementById("categoryFilterBar");
    const chips = [
        `<button class="chip ${activeCategoryId === null ? "active" : ""}" onclick="selectCategory(null)">Все</button>`
    ];
    categories.forEach(c => {
        chips.push(
            `<button class="chip ${activeCategoryId === c.id ? "active" : ""}" onclick="selectCategory(${c.id})">${c.name}</button>`
        );
    });
    bar.innerHTML = chips.join("");
}

function selectCategory(catId) {
    activeCategoryId = catId;
    renderCategoryFilters();
    renderProducts();
}

function renderCategorySelect() {
    const select = document.getElementById("prodCategory");
    const currentVal = select.value;
    select.innerHTML = `<option value="">Без категории</option>` +
        categories.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
    select.value = currentVal;
}

function renderProducts() {
    const grid = document.getElementById("productsGrid");
    const q = searchQuery.trim().toLowerCase();

    const filtered = products.filter(p => {
        if (activeCategoryId !== null && p.category_id !== activeCategoryId) return false;
        if (q) {
            const hay = `${p.name} ${p.description} ${p.tags} ${p.category_name}`.toLowerCase();
            if (!hay.includes(q)) return false;
        }
        return true;
    });

    if (!filtered.length) {
        grid.innerHTML = "<p>По вашему запросу товаров не найдено.</p>";
        return;
    }

    grid.innerHTML = filtered.map(p => {
        const outOfStock = p.stock <= 0;
        const tagsHtml = p.tags ? `<div class="card-tags">#${p.tags.split(",").map(t => t.trim()).filter(Boolean).join(" #")}</div>` : "";
        return `
            <article class="card">
                <img src="${p.image_url}" alt="${p.name}">
                <div class="card-body">
                    <div class="card-meta">
                        <span class="category-tag">${p.category_name}</span>
                        <span class="${outOfStock ? "stock-out" : "stock-ok"}">
                            ${outOfStock ? "Нет в наличии" : `В наличии: ${p.stock} шт.`}
                        </span>
                    </div>
                    <div class="card-title">${p.name}</div>
                    <div class="card-desc">${p.description}</div>
                    ${tagsHtml}
                    <div class="card-footer">
                        <span class="price">${p.price.toLocaleString("ru-RU")} ₽</span>
                        <button class="btn btn-primary btn-sm" ${outOfStock ? "disabled" : ""} onclick="addToCart(${p.id})">
                            ${outOfStock ? "Нет в наличии" : "В корзину"}
                        </button>
                    </div>
                </div>
            </article>
        `;
    }).join("");
}

function renderAdminList() {
    const list = document.getElementById("adminProductList");
    list.innerHTML = products.map(p => `
        <div class="admin-item">
            <div>
                <strong>${p.name}</strong> — ${p.price.toLocaleString("ru-RU")} ₽
                <small style="color:#64748b;">(${p.category_name} • Остаток: ${p.stock} шт.)</small>
            </div>
            <div class="admin-actions">
                <button class="btn btn-secondary btn-sm" onclick="editProduct(${p.id})">Изменить</button>
                <button class="btn btn-danger btn-sm" onclick="deleteProduct(${p.id})">Удалить</button>
            </div>
        </div>
    `).join("");
}

// --- Корзина и промокоды ---
function addToCart(id) {
    const product = products.find(p => p.id === id);
    if (!product || product.stock <= 0) return;

    const inCartQty = cart.filter(item => item.id === id).length;
    if (inCartQty >= product.stock) {
        alert(`На складе осталось только ${product.stock} шт. этого товара.`);
        return;
    }

    cart.push(product);
    saveCart();
    updateCartUI();
}

function removeFromCart(index) {
    cart.splice(index, 1);
    saveCart();
    updateCartUI();
}

function updateCartUI() {
    document.getElementById("cartCount").textContent = cart.length;
    const container = document.getElementById("cartItems");
    const subtotalEl = document.getElementById("cartSubtotal");
    const discountRow = document.getElementById("cartDiscountRow");
    const discountEl = document.getElementById("cartDiscount");
    const deliveryEl = document.getElementById("cartDelivery");
    const totalEl = document.getElementById("cartTotal");

    if (!cart.length) {
        container.innerHTML = "<p>Корзина пуста.</p>";
        subtotalEl.textContent = "0 ₽";
        discountRow.classList.add("hidden");
        deliveryEl.textContent = "0 ₽";
        totalEl.textContent = "0";
        return;
    }

    container.innerHTML = cart.map((item, idx) => `
        <div class="cart-item">
            <span>${item.name} — <strong>${item.price.toLocaleString("ru-RU")} ₽</strong></span>
            <button class="btn btn-danger btn-sm" onclick="removeFromCart(${idx})">&times;</button>
        </div>
    `).join("");

    const subtotal = cart.reduce((sum, item) => sum + item.price, 0);
    const discount = appliedPromo ? Math.round(subtotal * appliedPromo.discount_percent) / 100 : 0;
    const delivery = parseFloat(storeSettings.delivery_cost) || 0;
    const total = Math.max(0, subtotal - discount) + delivery;

    subtotalEl.textContent = `${subtotal.toLocaleString("ru-RU")} ₽`;
    if (discount > 0) {
        discountRow.classList.remove("hidden");
        discountEl.textContent = `-${discount.toLocaleString("ru-RU")} ₽ (${appliedPromo.code} -${appliedPromo.discount_percent}%)`;
    } else {
        discountRow.classList.add("hidden");
    }
    deliveryEl.textContent = delivery > 0 ? `${delivery.toLocaleString("ru-RU")} ₽` : "Бесплатно";
    totalEl.textContent = total.toLocaleString("ru-RU");
}

async function applyPromoCode() {
    const input = document.getElementById("cartPromoInput");
    const msgEl = document.getElementById("cartPromoMsg");
    const code = input.value.trim();

    if (!code) {
        appliedPromo = null;
        msgEl.textContent = "";
        updateCartUI();
        return;
    }

    const res = await fetch("/api/promocodes/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
    });
    const data = await res.json();

    if (!res.ok) {
        appliedPromo = null;
        msgEl.className = "promo-msg err";
        msgEl.textContent = data.error || "Промокод недействителен";
    } else {
        appliedPromo = data;
        msgEl.className = "promo-msg ok";
        msgEl.textContent = `Промокод ${data.code} применен: скидка ${data.discount_percent}%`;
    }
    updateCartUI();
}

// --- Авторизация ---
async function handleAuthSubmit(e) {
    e.preventDefault();
    const username = document.getElementById("authUsername").value.trim();
    const password = document.getElementById("authPassword").value;
    const errorEl = document.getElementById("authError");
    errorEl.textContent = "";

    const usernameRe = /^[A-Za-z0-9_]+$/;
    const passwordRe = /^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};:'",.<>/?]+$/;

    if (isRegisterMode) {
        if (username.length < 3) {
            errorEl.textContent = "Логин должен содержать минимум 3 символа";
            return;
        }
        if (!usernameRe.test(username)) {
            errorEl.textContent = "Логин должен состоять только из латинских букв, цифр и _";
            return;
        }
        if (password.length < 5) {
            errorEl.textContent = "Пароль должен содержать минимум 5 символов";
            return;
        }
        if (!passwordRe.test(password)) {
            errorEl.textContent = "Пароль должен содержать только латиницу, цифры и спецсимволы (без кириллицы и пробелов)";
            return;
        }
    } else if (!usernameRe.test(username) || !passwordRe.test(password)) {
        errorEl.textContent = "Логин и пароль должны быть написаны латиницей";
        return;
    }

    const url = isRegisterMode ? "/api/register" : "/api/login";
    const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (!res.ok) {
        errorEl.textContent = data.error || "Ошибка авторизации";
        return;
    }

    currentUser = data;
    renderAuthUI();
    closeModal("authModal");
    e.target.reset();
}

async function logout() {
    await fetch("/api/logout", { method: "POST" });
    currentUser = null;
    renderAuthUI();
}

// --- Админ-панель: Статистика ---
async function loadStats() {
    const res = await fetch("/api/admin/stats");
    if (!res.ok) return;
    const s = await res.json();

    document.getElementById("statsCards").innerHTML = `
        <div class="stat-card">
            <div class="stat-label">Общая выручка</div>
            <div class="stat-value accent">${s.total_revenue.toLocaleString("ru-RU")} ₽</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Всего заказов</div>
            <div class="stat-value">${s.total_orders}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">В работе / Выполнено</div>
            <div class="stat-value">${s.active_orders} / ${s.completed_orders}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Средний чек</div>
            <div class="stat-value">${s.avg_check.toLocaleString("ru-RU")} ₽</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Пользователей</div>
            <div class="stat-value">${s.total_users} <small style="font-size:0.75rem;color:#ef4444;">(блок: ${s.blocked_users})</small></div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Товаров (нет на складе)</div>
            <div class="stat-value">${s.total_products} <small style="font-size:0.75rem;color:#64748b;">(${s.out_of_stock_products})</small></div>
        </div>
    `;

    const topList = document.getElementById("topProductsList");
    if (!s.top_products.length) {
        topList.innerHTML = "<p style='color:#64748b;'>Пока нет завершенных продаж.</p>";
        return;
    }
    topList.innerHTML = s.top_products.map((p, idx) => `
        <div class="admin-item">
            <span><strong>#${idx + 1} ${p.name}</strong> — продано ${p.qty} шт.</span>
            <strong>${p.revenue.toLocaleString("ru-RU")} ₽</strong>
        </div>
    `).join("");
}

// --- Админ-панель: Товары ---
async function handleProductSubmit(e) {
    e.preventDefault();
    const id = document.getElementById("prodId").value;

    const formData = new FormData();
    formData.append("name", document.getElementById("prodName").value);
    formData.append("price", document.getElementById("prodPrice").value);
    formData.append("stock", document.getElementById("prodStock").value);
    formData.append("category_id", document.getElementById("prodCategory").value);
    formData.append("tags", document.getElementById("prodTags").value);
    formData.append("description", document.getElementById("prodDesc").value);

    const fileInput = document.getElementById("prodImage");
    if (fileInput.files.length > 0) {
        formData.append("image", fileInput.files[0]);
    }

    const url = id ? `/api/products/${id}` : "/api/products";
    const method = id ? "PUT" : "POST";

    const res = await fetch(url, { method, body: formData });

    if (res.ok) {
        resetAdminForm();
        await loadProducts();
    } else {
        const err = await res.json();
        alert(err.error || "Ошибка сохранения");
    }
}

function editProduct(id) {
    const p = products.find(item => item.id === id);
    if (!p) return;
    document.getElementById("prodId").value = p.id;
    document.getElementById("prodName").value = p.name;
    document.getElementById("prodPrice").value = p.price;
    document.getElementById("prodStock").value = p.stock;
    document.getElementById("prodCategory").value = p.category_id || "";
    document.getElementById("prodTags").value = p.tags || "";
    document.getElementById("prodDesc").value = p.description;
    document.getElementById("prodImage").value = "";
    document.getElementById("prodImageHint").textContent = "Оставьте пустым, чтобы сохранить текущее фото";

    const preview = document.getElementById("prodImagePreview");
    preview.src = p.image_url;
    preview.classList.remove("hidden");

    document.getElementById("prodSubmitBtn").textContent = "Сохранить изменения";
    document.getElementById("prodCancelEdit").classList.remove("hidden");
}

function resetAdminForm() {
    document.getElementById("productForm").reset();
    document.getElementById("prodId").value = "";
    document.getElementById("prodStock").value = "10";
    document.getElementById("prodImageHint").textContent = "Поддерживаются PNG, JPG, GIF, WEBP (до 5 МБ)";

    const preview = document.getElementById("prodImagePreview");
    preview.src = "";
    preview.classList.add("hidden");

    document.getElementById("prodSubmitBtn").textContent = "Добавить товар";
    document.getElementById("prodCancelEdit").classList.add("hidden");
}

async function deleteProduct(id) {
    if (!confirm("Удалить этот товар?")) return;
    const res = await fetch(`/api/products/${id}`, { method: "DELETE" });
    if (res.ok) await loadProducts();
}

// --- Админ-панель: Заказы ---
async function loadOrders() {
    const res = await fetch("/api/orders");
    if (!res.ok) return;
    const orders = await res.json();
    renderAdminOrders(orders);
}

function renderAdminOrders(orders) {
    const list = document.getElementById("adminOrdersList");
    if (!orders.length) {
        list.innerHTML = "<p>Заказов пока нет.</p>";
        return;
    }

    const isAdmin = currentUser && currentUser.role === "admin";
    const statuses = ["Новый", "В обработке", "Выполнен", "Отменен"];
    list.innerHTML = orders.map(o => `
        <div class="order-card">
            <div class="order-header">
                <strong>Заказ #${o.id} — ${o.customer_name}</strong>
                <span>${o.created_at}</span>
            </div>
            <ul class="order-items">
                ${o.items.map(i => `<li>${i.name} × ${i.qty} шт. (${i.price.toLocaleString("ru-RU")} ₽)</li>`).join("")}
            </ul>
            <div class="order-meta">
                ${o.promo_code ? `Промокод: <strong>${o.promo_code}</strong> (-${o.discount_amount.toLocaleString("ru-RU")} ₽) • ` : ""}
                Доставка: ${o.delivery_cost > 0 ? `${o.delivery_cost.toLocaleString("ru-RU")} ₽` : "Бесплатно"}
            </div>
            <div class="order-footer">
                <strong>Итого: ${o.total_price.toLocaleString("ru-RU")} ₽</strong>
                <div class="admin-actions">
                    <select class="status-select" onchange="updateOrderStatus(${o.id}, this.value)">
                        ${statuses.map(s => `<option value="${s}" ${o.status === s ? "selected" : ""}>${s}</option>`).join("")}
                    </select>
                    ${isAdmin ? `<button class="btn btn-danger btn-sm" onclick="deleteOrder(${o.id})">Удалить</button>` : ""}
                </div>
            </div>
        </div>
    `).join("");
}

async function updateOrderStatus(orderId, status) {
    await fetch(`/api/orders/${orderId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status })
    });
}

async function deleteOrder(orderId) {
    if (!confirm(`Удалить заказ #${orderId} из базы?`)) return;
    const res = await fetch(`/api/orders/${orderId}`, { method: "DELETE" });
    if (res.ok) await loadOrders();
}

// --- Админ-панель: Категории ---
function renderAdminCategories() {
    const list = document.getElementById("adminCategoriesList");
    if (!categories.length) {
        list.innerHTML = "<p>Категорий пока нет.</p>";
        return;
    }
    list.innerHTML = categories.map(c => `
        <div class="admin-item">
            <strong>${c.name}</strong>
            <button class="btn btn-danger btn-sm" onclick="deleteCategory(${c.id})">Удалить</button>
        </div>
    `).join("");
}

async function handleCategorySubmit(e) {
    e.preventDefault();
    const input = document.getElementById("newCategoryName");
    const res = await fetch("/api/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: input.value })
    });
    if (res.ok) {
        input.value = "";
        await loadCategories();
    } else {
        const err = await res.json();
        alert(err.error || "Ошибка создания категории");
    }
}

async function deleteCategory(catId) {
    if (!confirm("Удалить категорию? Товары останутся без категории.")) return;
    const res = await fetch(`/api/categories/${catId}`, { method: "DELETE" });
    if (res.ok) {
        if (activeCategoryId === catId) activeCategoryId = null;
        await loadCategories();
        await loadProducts();
    }
}

// --- Админ-панель: Промокоды ---
async function loadPromos() {
    const res = await fetch("/api/promocodes");
    if (!res.ok) return;
    const promos = await res.json();
    const list = document.getElementById("adminPromosList");

    if (!promos.length) {
        list.innerHTML = "<p>Промокодов пока нет.</p>";
        return;
    }
    list.innerHTML = promos.map(p => `
        <div class="admin-item">
            <div>
                <strong>${p.code}</strong> — скидка <strong>${p.discount_percent}%</strong>
                <span class="status-badge ${p.is_active ? "status-done" : "status-canceled"}">
                    ${p.is_active ? "Активен" : "Отключен"}
                </span>
                <div style="font-size:0.8rem; color:#64748b;">
                    Использован: ${p.used_count} / ${p.max_uses === 0 ? "∞" : p.max_uses}
                    ${p.expires_at ? ` • До ${p.expires_at}` : ""}
                </div>
            </div>
            <div class="admin-actions">
                <button class="btn btn-secondary btn-sm" onclick="togglePromo(${p.id})">
                    ${p.is_active ? "Отключить" : "Включить"}
                </button>
                <button class="btn btn-danger btn-sm" onclick="deletePromo(${p.id})">Удалить</button>
            </div>
        </div>
    `).join("");
}

async function handlePromoSubmit(e) {
    e.preventDefault();
    const res = await fetch("/api/promocodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            code: document.getElementById("promoCodeInput").value,
            discount_percent: document.getElementById("promoDiscountInput").value,
            max_uses: document.getElementById("promoMaxUsesInput").value,
            expires_at: document.getElementById("promoExpiresInput").value
        })
    });
    if (res.ok) {
        e.target.reset();
        document.getElementById("promoMaxUsesInput").value = "0";
        await loadPromos();
    } else {
        const err = await res.json();
        alert(err.error || "Ошибка создания промокода");
    }
}

async function togglePromo(id) {
    await fetch(`/api/promocodes/${id}/toggle`, { method: "PATCH" });
    await loadPromos();
}

async function deletePromo(id) {
    if (!confirm("Удалить этот промокод?")) return;
    await fetch(`/api/promocodes/${id}`, { method: "DELETE" });
    await loadPromos();
}

// --- Админ-панель: Пользователи ---
async function loadUsers() {
    const res = await fetch("/api/users");
    if (!res.ok) return;
    const users = await res.json();
    renderAdminUsers(users);
}

function renderAdminUsers(users) {
    const list = document.getElementById("adminUsersList");
    if (!users.length) {
        list.innerHTML = "<p>Пользователей нет.</p>";
        return;
    }

    const roles = [
        { value: "user", label: "Покупатель" },
        { value: "manager", label: "Менеджер" },
        { value: "admin", label: "Администратор" }
    ];

    list.innerHTML = users.map(u => {
        const isSelf = currentUser && u.id === currentUser.id;
        return `
            <div class="user-card ${u.is_blocked ? "is-blocked" : ""}">
                <div class="user-info">
                    <strong>${u.username}</strong>
                    ${isSelf ? '<span class="status-badge status-new">Вы</span>' : ""}
                    ${u.is_blocked ? '<span class="status-badge status-canceled">Заблокирован</span>' : ""}
                </div>
                <div class="user-controls">
                    <select class="status-select" ${isSelf ? "disabled" : ""} onchange="changeUserRole(${u.id}, this.value)">
                        ${roles.map(r => `<option value="${r.value}" ${u.role === r.value ? "selected" : ""}>${r.label}</option>`).join("")}
                    </select>
                    <button
                        class="btn btn-sm ${u.is_blocked ? "btn-secondary" : "btn-danger"}"
                        ${isSelf ? "disabled" : ""}
                        onclick="toggleUserBlock(${u.id})"
                    >
                        ${u.is_blocked ? "Разблокировать" : "Заблокировать"}
                    </button>
                </div>
            </div>
        `;
    }).join("");
}

async function changeUserRole(userId, role) {
    const res = await fetch(`/api/users/${userId}/role`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role })
    });
    if (!res.ok) {
        const err = await res.json();
        alert(err.error || "Не удалось изменить роль");
    }
    await loadUsers();
}

async function toggleUserBlock(userId) {
    const res = await fetch(`/api/users/${userId}/block`, { method: "PATCH" });
    if (!res.ok) {
        const err = await res.json();
        alert(err.error || "Не удалось изменить статус блокировки");
    }
    await loadUsers();
}

// --- Админ-панель: Логи ---
async function loadLogs() {
    const res = await fetch("/api/admin/logs");
    if (!res.ok) return;
    const logs = await res.json();
    const list = document.getElementById("adminLogsList");

    if (!logs.length) {
        list.innerHTML = "<p>Журнал действий пока пуст.</p>";
        return;
    }
    list.innerHTML = logs.map(l => `
        <div class="log-row">
            <div>
                <strong>${l.username}</strong> <small style="color:#64748b;">(${l.role})</small>: ${l.action}
            </div>
            <span class="log-time">${l.created_at}</span>
        </div>
    `).join("");
}

// --- Админ-панель: Настройки ---
function fillSettingsForm() {
    document.getElementById("setStoreName").value = storeSettings.store_name || "";
    document.getElementById("setHeroTitle").value = storeSettings.hero_title || "";
    document.getElementById("setHeroSubtitle").value = storeSettings.hero_subtitle || "";
    document.getElementById("setContactInfo").value = storeSettings.contact_info || "";
    document.getElementById("setDeliveryCost").value = storeSettings.delivery_cost || "0";
    document.getElementById("settingsSavedMsg").textContent = "";
}

async function handleSettingsSubmit(e) {
    e.preventDefault();
    const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            store_name: document.getElementById("setStoreName").value,
            hero_title: document.getElementById("setHeroTitle").value,
            hero_subtitle: document.getElementById("setHeroSubtitle").value,
            contact_info: document.getElementById("setContactInfo").value,
            delivery_cost: document.getElementById("setDeliveryCost").value
        })
    });
    if (res.ok) {
        storeSettings = await res.json();
        applyStoreSettingsUI();
        document.getElementById("settingsSavedMsg").textContent = "Настройки сохранены!";
    } else {
        const err = await res.json();
        alert(err.error || "Ошибка сохранения настроек");
    }
}

// --- Личный кабинет: Мои заказы ---
async function loadMyOrders() {
    const res = await fetch("/api/my-orders");
    if (!res.ok) return;
    const orders = await res.json();
    renderMyOrders(orders);
}

function getStatusClass(status) {
    const map = {
        "Новый": "status-new",
        "В обработке": "status-progress",
        "Выполнен": "status-done",
        "Отменен": "status-canceled"
    };
    return map[status] || "status-new";
}

function renderMyOrders(orders) {
    const list = document.getElementById("myOrdersList");
    if (!orders.length) {
        list.innerHTML = "<p>Вы еще не оформляли заказы.</p>";
        return;
    }

    list.innerHTML = orders.map(o => `
        <div class="order-card">
            <div class="order-header">
                <strong>Заказ #${o.id}</strong>
                <span>${o.created_at}</span>
            </div>
            <ul class="order-items">
                ${o.items.map(i => `<li>${i.name} × ${i.qty} шт. (${i.price.toLocaleString("ru-RU")} ₽)</li>`).join("")}
            </ul>
            <div class="order-footer">
                <strong>Итого: ${o.total_price.toLocaleString("ru-RU")} ₽</strong>
                <span class="status-badge ${getStatusClass(o.status)}">${o.status}</span>
            </div>
        </div>
    `).join("");
}

// --- Переключение вкладок и события ---
function openModal(id) { document.getElementById(id).classList.remove("hidden"); }
function closeModal(id) { document.getElementById(id).classList.add("hidden"); }

function switchAdminTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.toggle("active", b.dataset.tab === tabId);
    });
    document.querySelectorAll(".tab-content").forEach(c => {
        c.classList.toggle("hidden", c.id !== tabId);
    });
    if (tabId === "statsTab") loadStats();
    if (tabId === "ordersTab") loadOrders();
    if (tabId === "categoriesTab") loadCategories();
    if (tabId === "promosTab") loadPromos();
    if (tabId === "usersTab") loadUsers();
    if (tabId === "logsTab") loadLogs();
    if (tabId === "settingsTab") fillSettingsForm();
}

function setupEvents() {
    document.getElementById("cartBtn").onclick = () => { updateCartUI(); openModal("cartModal"); };
    document.getElementById("applyPromoBtn").onclick = applyPromoCode;
    document.getElementById("adminBtn").onclick = () => {
        const defaultTab = currentUser && currentUser.role === "admin" ? "statsTab" : "productsTab";
        switchAdminTab(defaultTab);
        openModal("adminModal");
    };

    document.getElementById("catalogSearch").addEventListener("input", (e) => {
        searchQuery = e.target.value;
        renderProducts();
    });

    document.getElementById("authForm").onsubmit = handleAuthSubmit;
    document.getElementById("productForm").onsubmit = handleProductSubmit;
    document.getElementById("categoryForm").onsubmit = handleCategorySubmit;
    document.getElementById("promoForm").onsubmit = handlePromoSubmit;
    document.getElementById("settingsForm").onsubmit = handleSettingsSubmit;
    document.getElementById("prodCancelEdit").onclick = resetAdminForm;

    document.getElementById("prodImage").addEventListener("change", (e) => {
        const file = e.target.files[0];
        const preview = document.getElementById("prodImagePreview");

        if (file) {
            preview.src = URL.createObjectURL(file);
            preview.classList.remove("hidden");
        } else {
            preview.src = "";
            preview.classList.add("hidden");
        }
    });

    document.getElementById("checkoutBtn").onclick = async () => {
        if (!cart.length) return;
        const res = await fetch("/api/orders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                product_ids: cart.map(item => item.id),
                promo_code: appliedPromo ? appliedPromo.code : ""
            })
        });

        if (res.ok) {
            const order = await res.json();
            alert(`Заказ #${order.id} на сумму ${order.total_price.toLocaleString("ru-RU")} ₽ успешно оформлен!`);
            cart = [];
            appliedPromo = null;
            document.getElementById("cartPromoInput").value = "";
            document.getElementById("cartPromoMsg").textContent = "";
            saveCart();
            await loadProducts(); // Обновляем остатки на складе
            closeModal("cartModal");
        } else {
            const err = await res.json();
            alert(err.error || "Не удалось оформить заказ");
        }
    };

    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.onclick = () => switchAdminTab(btn.dataset.tab);
    });

    document.getElementById("authSwitchLink").onclick = (e) => {
        e.preventDefault();
        isRegisterMode = !isRegisterMode;
        document.getElementById("authTitle").textContent = isRegisterMode ? "Регистрация" : "Вход в аккаунт";
        document.getElementById("authSubmitBtn").textContent = isRegisterMode ? "Создать аккаунт" : "Войти";
        document.getElementById("authSwitchText").textContent = isRegisterMode ? "Уже есть аккаунт?" : "Нет аккаунта?";
        document.getElementById("authSwitchLink").textContent = isRegisterMode ? "Войти" : "Зарегистрироваться";
        document.getElementById("authError").textContent = "";
    };

    document.querySelectorAll("[data-close]").forEach(btn => {
        btn.onclick = () => closeModal(btn.dataset.close);
    });
}
