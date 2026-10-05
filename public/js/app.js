/**
 * GALILEA ATELIER - Frontend Application Logic
 * Joyería Minimalista & Pasarela de Pagos Argentina
 */

// Estado global de la aplicación
const AppState = {
  products: [],
  filteredProducts: [],
  categories: [],
  activeCategory: 'todos',
  activeMetal: 'todos',
  sortOrder: 'featured',
  searchQuery: '',
  cart: [],
  selectedProduct: null,
  selectedSize: null,
  activePaymentTab: 'mercadopago',
  appliedPromo: null
};

// Formateador de moneda para Argentina (ARS)
const formatARS = (amount) => {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0
  }).format(amount);
};

// --- INICIALIZACIÓN ---

document.addEventListener('DOMContentLoaded', () => {
  initIcons();
  loadCartFromStorage();
  fetchStoreSettings();
  fetchCategories();
  fetchProducts();
  setupEventListeners();
  updateCartUI();
  initScrollAnimations();
  initAIChatAdvisor();
});

async function fetchStoreSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (data.success && data.settings) {
      const s = data.settings;
      // Actualizar Ticker Superior Continuo (Marquee estilo Brooki Bakehouse)
      const tickerEls = document.querySelectorAll('.ticker-content');
      if (tickerEls.length > 0 && s.ticker_text) {
        const parts = s.ticker_text.split('/');
        const sparkleIcon = (window.ICONS && window.ICONS.sparkle) ? window.ICONS.sparkle : '';
        const html = parts.map((p) => `
          <span>${p.trim()}</span>
          <span class="ticker-sep">${sparkleIcon}</span>
        `).join('');
        tickerEls.forEach(el => el.innerHTML = html);
      }

      // Actualizar Portada (Hero)
      const heroTag = document.querySelector('.hero-tag');
      const heroTitle = document.querySelector('.hero-title');
      const heroDesc = document.querySelector('.hero-desc');

      if (heroTag && s.hero_tag) heroTag.textContent = s.hero_tag;
      if (heroTitle && s.hero_title) heroTitle.innerHTML = s.hero_title.includes('<em>') ? s.hero_title : s.hero_title;
      if (heroDesc && s.hero_desc) heroDesc.textContent = s.hero_desc;
    }
  } catch (e) {
    console.warn('Configuración por defecto en uso');
  }
}

// Observador reutilizable para animaciones de deslizamiento al hacer scroll (Estilo Brooki Bakehouse)
let scrollObserver = null;

function initScrollAnimations() {
  if (!('IntersectionObserver' in window)) {
    document.querySelectorAll('.fade-in-scroll').forEach(el => el.classList.add('is-visible'));
    return;
  }

  if (!scrollObserver) {
    scrollObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          scrollObserver.unobserve(entry.target);
          setTimeout(() => {
            if (entry.target && entry.target.style) {
              entry.target.style.transitionDelay = '0s';
            }
          }, 1100);
        }
      });
    }, { threshold: 0.04, rootMargin: '0px 0px -40px 0px' });

    // Garantizar que todos los elementos al pie de página se revelen al llegar al final del scroll
    window.addEventListener('scroll', () => {
      const scrollPos = window.innerHeight + window.scrollY;
      const docHeight = document.documentElement.scrollHeight;
      if (scrollPos >= docHeight - 120) {
        document.querySelectorAll('.fade-in-scroll:not(.is-visible)').forEach(el => {
          el.classList.add('is-visible');
          if (scrollObserver) scrollObserver.unobserve(el);
        });
      }
    }, { passive: true });
  }

  document.querySelectorAll('.fade-in-scroll:not(.is-visible)').forEach(el => {
    scrollObserver.observe(el);
  });
}

// Inyectar iconos SVG en placeholders marcados con data-icon
function initIcons() {
  document.querySelectorAll('[data-icon]').forEach(el => {
    const iconName = el.getAttribute('data-icon');
    if (window.ICONS && window.ICONS[iconName]) {
      el.innerHTML = window.ICONS[iconName];
    }
  });
}

// --- PERSISTENCIA DE CARRITO ---

function loadCartFromStorage() {
  try {
    const stored = localStorage.getItem('galilea_cart');
    if (stored) {
      AppState.cart = JSON.parse(stored);
    }
  } catch (e) {
    console.error('Error cargando carrito:', e);
    AppState.cart = [];
  }
}

function saveCartToStorage() {
  try {
    localStorage.setItem('galilea_cart', JSON.stringify(AppState.cart));
  } catch (e) {
    console.error('Error guardando carrito:', e);
  }
}

// --- CARGA DE DATOS DESDE LA API ---

async function fetchProducts() {
  const gridEl = document.getElementById('products-grid');
  gridEl.innerHTML = `
    <div style="grid-column: 1 / -1; text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
      Cargando catálogo exclusivo de Galilea Atelier...
    </div>
  `;

  try {
    const url = new URL('/api/products', window.location.origin);
    if (AppState.activeCategory !== 'todos') url.searchParams.set('category', AppState.activeCategory);
    if (AppState.activeMetal !== 'todos') url.searchParams.set('metal', AppState.activeMetal);
    if (AppState.sortOrder !== 'featured') url.searchParams.set('sort', AppState.sortOrder);
    if (AppState.searchQuery) url.searchParams.set('q', AppState.searchQuery);

    const res = await fetch(url);
    const data = await res.json();

    if (data.success && Array.isArray(data.products)) {
      AppState.products = data.products;
      AppState.filteredProducts = data.products;
      renderProducts();
      updateCounter();
    }
  } catch (err) {
    console.warn('API error, cargando datos locales de contingencia:', err);
    // Contingencia local si el server está cargando
    renderProducts();
  }
}

async function fetchCategories() {
  try {
    const res = await fetch('/api/categories');
    const data = await res.json();
    if (data.success) {
      AppState.categories = data.categories;
      renderCategories();
    }
  } catch (err) {
    console.warn('No se pudieron obtener las categorías dinámicas');
  }
}

// --- RENDERIZADO DE LA INTERFAZ ---

function renderCategories() {
  const barEl = document.getElementById('category-filter-bar');
  if (!barEl) return;

  barEl.innerHTML = AppState.categories.map(cat => `
    <button class="cat-btn ${AppState.activeCategory === cat.id ? 'active' : ''}" data-category="${cat.id}">
      <span>${cat.label}</span>
      <span class="cat-count">(${cat.count})</span>
    </button>
  `).join('');

  barEl.querySelectorAll('.cat-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const targetCat = btn.getAttribute('data-category');
      selectNavCategory(targetCat);
    });
  });
}

function selectNavCategory(catId) {
  AppState.activeCategory = catId;
  renderCategories();
  fetchProducts();

  // Actualizar estado activo en la barra de navegación superior (Desktop)
  document.querySelectorAll('.nav-links .nav-item').forEach(item => {
    const fnStr = item.getAttribute('onclick') || '';
    if (fnStr.includes(`'${catId}'`)) {
      item.classList.add('active');
    } else if (catId === 'todos' && fnStr.includes("'todos'")) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // Actualizar estado activo en la franja móvil de categorías (Mobile)
  document.querySelectorAll('.mobile-cat-strip .mobile-cat-pill').forEach(pill => {
    const fnStr = pill.getAttribute('onclick') || '';
    if (fnStr.includes(`'${catId}'`)) {
      pill.classList.add('active');
    } else if (catId === 'todos' && fnStr.includes("'todos'")) {
      pill.classList.add('active');
    } else {
      pill.classList.remove('active');
    }
  });

  const catalogEl = document.getElementById('catalogo');
  if (catalogEl) {
    catalogEl.scrollIntoView({ behavior: 'smooth' });
  }
}

function updateCounter() {
  const countEl = document.getElementById('catalog-count');
  if (countEl) {
    const count = AppState.filteredProducts.length;
    countEl.textContent = `${count} ${count === 1 ? 'pieza' : 'piezas'}`;
  }
}

// Helper para asignar variantes cromáticas pastel según el tipo de insignia
function getBadgeStyleClass(badge) {
  if (!badge) return '';
  const lower = badge.toLowerCase();
  if (lower.includes('best') || lower.includes('vendido') || lower.includes('off') || lower.includes('descuento') || lower.includes('promo')) {
    return 'badge-rose';
  }
  if (lower.includes('joyería') || lower.includes('joyeria') || lower.includes('diamante') || lower.includes('nuevo') || lower.includes('exclusivo')) {
    return 'badge-blush';
  }
  return 'badge-beige';
}

function renderProducts() {
  const gridEl = document.getElementById('products-grid');
  if (!gridEl) return;

  if (AppState.filteredProducts.length === 0) {
    gridEl.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 5rem 1rem;">
        <p class="serif-font" style="font-size: 1.6rem; color: var(--text-primary); margin-bottom: 0.5rem;">No se encontraron piezas con esos criterios</p>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1.5rem;">Intentá seleccionando otra categoría o limpiando los filtros.</p>
        <button class="btn-luxury-outline" id="btn-reset-filters">Ver Todo el Catálogo</button>
      </div>
    `;
    const resetBtn = document.getElementById('btn-reset-filters');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        AppState.activeCategory = 'todos';
        AppState.activeMetal = 'todos';
        AppState.searchQuery = '';
        renderCategories();
        fetchProducts();
      });
    }
    return;
  }

  gridEl.innerHTML = AppState.filteredProducts.map((product, idx) => {
    const cuota3 = Math.round(product.price / 3);
    const badgeClass = getBadgeStyleClass(product.badge);
    const isMobile = window.innerWidth < 768;
    const cols = isMobile ? 2 : 4;
    const staggerDelay = ((idx % cols) * 0.12).toFixed(2);
    return `
      <article class="product-card fade-in-scroll" style="transition-delay: ${staggerDelay}s;" data-product-id="${product.id}">
        <div class="product-media">
          ${product.badge ? `<span class="card-badge ${badgeClass}">${product.badge}</span>` : ''}
          <img src="${product.primary_image}" alt="${product.name}" class="product-img img-primary" loading="lazy">
          <img src="${product.secondary_image || product.primary_image}" alt="${product.name} en detalle" class="product-img img-secondary" loading="lazy">
          
          <div class="card-overlay-actions">
            <button class="btn-card-action btn-quick-view" data-id="${product.id}">
              ${window.ICONS.eye}
              <span>Vista Rápida</span>
            </button>
            <button class="btn-card-action btn-quick-add" data-id="${product.id}">
              ${window.ICONS.bag}
              <span>Añadir</span>
            </button>
          </div>
        </div>

        <div class="product-details">
          <span class="product-category-tag">${product.metal} · ${product.category_label}</span>
          <h3 class="product-title" data-id="${product.id}">${product.name}</h3>
          <div class="product-price">${formatARS(product.price)}</div>
          <div class="product-installments">3 cuotas sin interés de ${formatARS(cuota3)}</div>
        </div>
      </article>
    `;
  }).join('');

  // Eventos en tarjetas
  gridEl.querySelectorAll('.btn-quick-view, .product-title').forEach(el => {
    el.addEventListener('click', (e) => {
      const id = el.closest('[data-product-id]').getAttribute('data-product-id');
      const prod = AppState.products.find(p => p.id === id);
      if (prod) openQuickView(prod);
    });
  });

  gridEl.querySelectorAll('.btn-quick-add').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      el.classList.add('btn-pulse-active');
      setTimeout(() => el.classList.remove('btn-pulse-active'), 350);
      const id = el.getAttribute('data-id');
      const prod = AppState.products.find(p => p.id === id);
      if (prod) {
        const defaultSize = prod.sizes && prod.sizes.length > 0 ? prod.sizes[0] : 'Único';
        addToCart(prod, defaultSize, 1);
        showToast(`"${prod.name}" añadida a la bolsa`);
      }
    });
  });

  initScrollAnimations();
}

// --- VISTA RÁPIDA (MODAL) ---

function openQuickView(product) {
  AppState.selectedProduct = product;
  AppState.selectedSize = product.sizes && product.sizes.length > 0 ? product.sizes[0] : 'Único';

  const modalOverlay = document.getElementById('quickview-modal-overlay');
  const modalContent = document.getElementById('quickview-modal-content');

  const cuota3 = Math.round(product.price / 3);
  const cuota6 = Math.round(product.price / 6);

  // Tabla de especificaciones
  let specsHtml = '';
  if (product.specs) {
    specsHtml = `
      <table class="modal-specs-table">
        <tbody>
          ${Object.entries(product.specs).map(([key, val]) => `
            <tr>
              <td>${key.replace('_', ' ')}</td>
              <td>${val}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  // Selector de talles
  let sizesHtml = '';
  if (product.sizes && product.sizes.length > 0) {
    sizesHtml = `
      <div style="margin-top: 0.5rem;">
        <div class="size-selector-label">
          <span>Seleccionar Medida / Talle:</span>
          <span class="size-guide-link">${window.ICONS.ruler} Guía Oficial de Talles</span>
        </div>
        <div class="size-options">
          ${product.sizes.map((sz, idx) => `
            <button class="size-btn ${idx === 0 ? 'active' : ''}" data-size="${sz}">${sz}</button>
          `).join('')}
        </div>
      </div>
    `;
  }

  modalContent.innerHTML = `
    <div class="product-modal-card">
      <button class="btn-close-modal" id="btn-close-quickview" aria-label="Cerrar modal">
        ${window.ICONS.close}
      </button>

      <div class="modal-media-col">
        <img src="${product.primary_image}" alt="${product.name}" class="modal-main-img" id="modal-image-view">
      </div>

      <div class="modal-details-col">
        <div>
          <span class="modal-tag">${product.metal} · ${product.category_label}</span>
          <h2 class="modal-title">${product.name}</h2>
        </div>

        <div>
          <div class="modal-price">${formatARS(product.price)}</div>
          <div class="modal-installments">3 cuotas sin interés de ${formatARS(cuota3)} o 6 de ${formatARS(cuota6)}</div>
        </div>

        <p class="modal-desc">${product.description}</p>

        ${sizesHtml}

        <div>
          <button class="btn-luxury" style="width: 100%; margin-top: 0.8rem;" id="btn-modal-add-cart">
            ${window.ICONS.bag}
            <span>Añadir a la Bolsa de Compras</span>
          </button>
        </div>

        <div style="margin-top: 0.5rem;">
          <span style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gold-dark); font-weight: 600;">Detalles de Orfebrería</span>
          ${specsHtml}
        </div>
      </div>
    </div>
  `;

  modalOverlay.classList.add('open');
  document.body.style.overflow = 'hidden';

  // Listeners de modal
  document.getElementById('btn-close-quickview').addEventListener('click', closeQuickView);

  modalContent.querySelectorAll('.size-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      modalContent.querySelectorAll('.size-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      AppState.selectedSize = btn.getAttribute('data-size');
    });
  });

  document.getElementById('btn-modal-add-cart').addEventListener('click', () => {
    addToCart(product, AppState.selectedSize, 1);
    closeQuickView();
    openCartDrawer();
    showToast(`"${product.name}" añadida a la bolsa`);
  });
}

function closeQuickView() {
  const modalOverlay = document.getElementById('quickview-modal-overlay');
  if (modalOverlay) {
    modalOverlay.classList.remove('open');
    document.body.style.overflow = '';
  }
}

// --- BOLSA DE COMPRAS (DRAWER) ---

function addToCart(product, size = 'Único', quantity = 1) {
  const existingIdx = AppState.cart.findIndex(
    item => item.product.id === product.id && item.size === size
  );

  if (existingIdx > -1) {
    AppState.cart[existingIdx].quantity += quantity;
  } else {
    AppState.cart.push({
      product,
      size,
      quantity
    });
  }

  saveCartToStorage();
  updateCartUI();
}

function updateCartQuantity(index, delta) {
  if (AppState.cart[index]) {
    AppState.cart[index].quantity += delta;
    if (AppState.cart[index].quantity <= 0) {
      AppState.cart.splice(index, 1);
    }
    saveCartToStorage();
    updateCartUI();
  }
}

function removeCartItem(index) {
  AppState.cart.splice(index, 1);
  saveCartToStorage();
  updateCartUI();
}

function updateCartUI() {
  const countBadges = document.querySelectorAll('.cart-count-badge');
  const totalCount = AppState.cart.reduce((acc, item) => acc + item.quantity, 0);

  countBadges.forEach(b => {
    b.textContent = totalCount;
    b.style.display = totalCount > 0 ? 'flex' : 'none';
  });

  const bodyEl = document.getElementById('cart-items-body');
  const footerEl = document.getElementById('cart-drawer-footer');

  if (!bodyEl) return;

  if (AppState.cart.length === 0) {
    bodyEl.innerHTML = `
      <div class="cart-empty-state">
        <div style="color: var(--gold-primary); opacity: 0.6;">
          <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.2">
            <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>
          </svg>
        </div>
        <h3 class="cart-empty-title">Tu bolsa de compras está vacía</h3>
        <p style="font-size: 0.85rem; line-height: 1.6;">Descubrí nuestras piezas de orfebrería y sumalas para adquirir con envío asegurado.</p>
        <button class="btn-luxury" id="btn-start-shopping" style="margin-top: 1rem;">Explorar Colección</button>
      </div>
    `;
    if (footerEl) footerEl.style.display = 'none';

    const startBtn = document.getElementById('btn-start-shopping');
    if (startBtn) {
      startBtn.addEventListener('click', () => {
        closeCartDrawer();
        const catalogSec = document.getElementById('catalogo');
        if (catalogSec) catalogSec.scrollIntoView({ behavior: 'smooth' });
      });
    }
    return;
  }

  if (footerEl) footerEl.style.display = 'flex';

  const subtotal = AppState.cart.reduce((acc, item) => acc + (item.product.price * item.quantity), 0);
  const cuota3 = Math.round(subtotal / 3);

  bodyEl.innerHTML = AppState.cart.map((item, idx) => `
    <div class="cart-item-row">
      <img src="${item.product.primary_image}" alt="${item.product.name}" class="cart-item-img">
      <div class="cart-item-info">
        <h4 class="cart-item-name">${item.product.name}</h4>
        <span class="cart-item-size">Medida: ${item.size}</span>
        <div class="cart-item-price">${formatARS(item.product.price * item.quantity)}</div>
        <div class="qty-control">
          <button class="qty-btn" onclick="updateCartQuantity(${idx}, -1)">${window.ICONS.minus}</button>
          <span class="qty-num">${item.quantity}</span>
          <button class="qty-btn" onclick="updateCartQuantity(${idx}, 1)">${window.ICONS.plus}</button>
        </div>
      </div>
      <button class="btn-remove-item" onclick="removeCartItem(${idx})" title="Eliminar pieza">
        ${window.ICONS.close}
      </button>
    </div>
  `).join('');

  // Actualizar sumas en footer
  const subtotalEl = document.getElementById('cart-subtotal-val');
  const totalEl = document.getElementById('cart-total-val');
  const cuotasEl = document.getElementById('cart-cuotas-text');

  if (subtotalEl) subtotalEl.textContent = formatARS(subtotal);
  if (totalEl) totalEl.textContent = formatARS(subtotal);
  if (cuotasEl) cuotasEl.textContent = `Hasta 3 cuotas sin interés de ${formatARS(cuota3)} con Visa, Mastercard y Amex`;
}

function openCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  const overlay = document.getElementById('drawer-overlay');
  if (drawer && overlay) {
    drawer.classList.add('open');
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

function closeCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  const overlay = document.getElementById('drawer-overlay');
  if (drawer && overlay) {
    drawer.classList.remove('open');
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }
}

// --- CHECKOUT FLOW (ARGENTINA) ---

function openCheckoutModal() {
  if (AppState.cart.length === 0) {
    showToast('Añadí al menos una pieza a la bolsa para pagar');
    return;
  }

  closeCartDrawer();
  const modalOverlay = document.getElementById('checkout-modal-overlay');
  const modalContent = document.getElementById('checkout-modal-content');

  const subtotal = AppState.cart.reduce((acc, item) => acc + (item.product.price * item.quantity), 0);
  const transferDiscount = subtotal * 0.15;
  const transferTotal = subtotal - transferDiscount;

  modalContent.innerHTML = `
    <div class="checkout-modal-card" id="checkout-card-container">
      <div class="checkout-header">
        <div>
          <h2 class="checkout-title">Finalizar Adquisición</h2>
          <span class="checkout-subtitle">Checkout Seguro · Envíos Asegurados a Toda la República Argentina</span>
        </div>
        <button class="btn-close-modal" id="btn-close-checkout">${window.ICONS.close}</button>
      </div>

      <div class="checkout-grid" id="checkout-main-grid">
        <!-- Columna Izquierda: Datos del Comprador & Envío -->
        <div>
          <h3 class="checkout-section-title">
            ${window.ICONS.shipping}
            <span>1. Datos de Entrega & Facturación</span>
          </h3>

          <form id="checkout-shipping-form" onsubmit="event.preventDefault()">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">Nombre y Apellido</label>
                <input type="text" id="chk-name" class="form-input" placeholder="Ej. Camila Navarro" required value="Camila Navarro">
              </div>
              <div class="form-group">
                <label class="form-label">DNI / CUIL (Requerido p/ Facturación)</label>
                <input type="text" id="chk-dni" class="form-input" placeholder="Ej. 34.890.123" required value="34890123">
              </div>
            </div>

            <div class="form-row">
              <div class="form-group">
                <label class="form-label">Correo Electrónico</label>
                <input type="email" id="chk-email" class="form-input" placeholder="nombre@ejemplo.com" required value="camila.navarro@gmail.com">
              </div>
              <div class="form-group">
                <label class="form-label">Teléfono / WhatsApp</label>
                <input type="tel" id="chk-phone" class="form-input" placeholder="Ej. +54 9 11 4050-9988" required value="+54 9 11 4050-9988">
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Dirección de Entrega</label>
              <input type="text" id="chk-address" class="form-input" placeholder="Calle y Altura, Piso / Depto" required value="Av. Alvear 1850, Piso 6B">
            </div>

            <div class="form-row">
              <div class="form-group">
                <label class="form-label">Provincia</label>
                <select id="chk-province" class="form-select">
                  <option value="CABA" selected>Ciudad Autónoma de Buenos Aires</option>
                  <option value="Buenos Aires">Provincia de Buenos Aires</option>
                  <option value="Córdoba">Córdoba</option>
                  <option value="Santa Fe">Santa Fe</option>
                  <option value="Mendoza">Mendoza</option>
                  <option value="Salta">Salta</option>
                  <option value="Neuquén">Neuquén</option>
                  <option value="Tucumán">Tucumán</option>
                  <option value="Entre Ríos">Entre Ríos</option>
                  <option value="Otras Provincias">Otras Provincias (Andreani Asegurado)</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">Código Postal (CP)</label>
                <input type="text" id="chk-zip" class="form-input" placeholder="Ej. C1014AAD" required value="C1014AAD">
              </div>
            </div>
          </form>

          <!-- Resumen de items -->
          <div class="order-summary-box" style="margin-top: 1.5rem;">
            <div style="font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gold-dark); font-weight: 600; margin-bottom: 0.8rem;">
              Piezas en tu pedido (${AppState.cart.length})
            </div>
            <div class="order-items-mini">
              ${AppState.cart.map(it => `
                <div class="order-item-mini-row">
                  <span>${it.quantity}x ${it.product.name} (${it.size})</span>
                  <span style="font-weight: 600;">${formatARS(it.product.price * it.quantity)}</span>
                </div>
              `).join('')}
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-top: 0.5rem;">
              <span>Envío Asegurado Andreani / Correo:</span>
              <span style="color: var(--status-success); font-weight: 600;">Bonificado (Gratis)</span>
            </div>
          </div>
        </div>

        <!-- Columna Derecha: Métodos de Pago Argentina -->
        <div>
          <h3 class="checkout-section-title">
            ${window.ICONS.creditCard}
            <span>2. Selección de Medio de Pago</span>
          </h3>

          <div class="payment-tabs">
            <button class="payment-tab-btn ${AppState.activePaymentTab === 'mercadopago' ? 'active' : ''}" data-tab="mercadopago">
              ${window.ICONS.badgeMercadoPago}
              <span>Mercado Pago</span>
            </button>
            <button class="payment-tab-btn ${AppState.activePaymentTab === 'card' ? 'active' : ''}" data-tab="card">
              ${window.ICONS.creditCard}
              <span>Tarjetas Directas</span>
            </button>
            <button class="payment-tab-btn ${AppState.activePaymentTab === 'transfer' ? 'active' : ''}" data-tab="transfer">
              ${window.ICONS.bank}
              <span>Transferencia</span>
              <span class="tab-badge-discount">15% OFF</span>
            </button>
          </div>

          <!-- PANEL 1: MERCADO PAGO -->
          <div class="payment-panel ${AppState.activePaymentTab === 'mercadopago' ? 'active' : ''}" id="panel-mercadopago">
            <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 1.2rem; line-height: 1.6;">
              Pagá a través de la pasarela líder de Argentina. Podés utilizar dinero en cuenta de Mercado Pago o tarjetas de débito/crédito con hasta 6 cuotas bancarias.
            </p>
            <div class="card-brands-row">
              ${window.ICONS.badgeVisa}
              ${window.ICONS.badgeMastercard}
              ${window.ICONS.badgeAmex}
              ${window.ICONS.badgeMercadoPago}
            </div>
            <div style="background-color: var(--bg-surface); padding: 1rem; border-radius: var(--radius-xs); border: 1px solid var(--border-light); margin-bottom: 1.2rem; font-size: 0.8rem;">
              <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem;">
                <span>Total de la Orden:</span>
                <span style="font-weight: 700;">${formatARS(subtotal)}</span>
              </div>
              <div style="color: var(--status-success); font-size: 0.75rem;">
                3 cuotas sin interés de ${formatARS(Math.round(subtotal / 3))} o 6 cuotas de ${formatARS(Math.round(subtotal / 6))}
              </div>
            </div>
            <button class="btn-luxury" style="width: 100%;" id="btn-pay-mp">
              ${window.ICONS.lock}
              <span>Continuar con Mercado Pago</span>
            </button>
          </div>

          <!-- PANEL 2: TARJETAS DIRECTAS CON CUOTAS ARGENTINAS -->
          <div class="payment-panel ${AppState.activePaymentTab === 'card' ? 'active' : ''}" id="panel-card">
            <div class="card-brands-row">
              ${window.ICONS.badgeVisa}
              ${window.ICONS.badgeMastercard}
              ${window.ICONS.badgeAmex}
            </div>
            <form id="direct-card-form" onsubmit="event.preventDefault()">
              <div class="form-group">
                <label class="form-label">Número de Tarjeta</label>
                <input type="text" id="card-num" class="form-input" placeholder="4509 2300 1234 5678" maxlength="19" value="4509 2341 8762 9012">
              </div>
              <div class="form-group">
                <label class="form-label">Nombre del Titular (como figura en el plástico)</label>
                <input type="text" id="card-holder" class="form-input" placeholder="CAMILA NAVARRO" value="CAMILA NAVARRO">
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">Vencimiento</label>
                  <input type="text" id="card-exp" class="form-input" placeholder="MM/AA" maxlength="5" value="08/29">
                </div>
                <div class="form-group">
                  <label class="form-label">Código CVV</label>
                  <input type="password" id="card-cvv" class="form-input" placeholder="123" maxlength="4" value="789">
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">Planes de Cuotas Disponibles en Argentina</label>
                <select id="card-installments" class="form-select">
                  <option value="1">1 cuota de ${formatARS(subtotal)} (Sin recargo)</option>
                  <option value="3" selected>3 cuotas SIN INTERÉS de ${formatARS(Math.round(subtotal / 3))}</option>
                  <option value="6">6 cuotas fijas de ${formatARS(Math.round(subtotal / 6))}</option>
                </select>
              </div>
              <button class="btn-luxury" style="width: 100%; margin-top: 0.5rem;" id="btn-pay-card">
                ${window.ICONS.lock}
                <span>Confirmar Pago de ${formatARS(subtotal)}</span>
              </button>
            </form>
          </div>

          <!-- PANEL 3: TRANSFERENCIA BANCARIA CON 15% OFF -->
          <div class="payment-panel ${AppState.activePaymentTab === 'transfer' ? 'active' : ''}" id="panel-transfer">
            <div style="background-color: var(--gold-tint); border: 1px solid var(--gold-light); padding: 0.9rem; border-radius: var(--radius-xs); margin-bottom: 1.2rem;">
              <div style="font-size: 0.8rem; font-weight: 600; color: var(--gold-dark); margin-bottom: 0.2rem;">
                Beneficio Exclusivo: 15% de Descuento Inmediato
              </div>
              <div style="font-size: 0.75rem; color: var(--text-secondary);">
                Subtotal regular: <s>${formatARS(subtotal)}</s><br>
                <strong style="color: var(--text-primary); font-size: 0.9rem;">Total Bonificado: ${formatARS(transferTotal)}</strong>
              </div>
            </div>
            <p style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.6; margin-bottom: 1.2rem;">
              Al confirmar, te brindamos los datos de CBU/Alias de nuestra cuenta bancaria en Santander / Galicia y reservamos tus joyas por 24 hs.
            </p>
            <button class="btn-luxury" style="width: 100%;" id="btn-pay-transfer">
              ${window.ICONS.check}
              <span>Generar Orden con 15% OFF (${formatARS(transferTotal)})</span>
            </button>
          </div>

          <!-- Garantías al pie -->
          <div class="trust-badges-bar">
            <div class="trust-badge-item">
              ${window.ICONS.shield}
              <span>Certificado 18K / 925</span>
            </div>
            <div class="trust-badge-item">
              ${window.ICONS.lock}
              <span>Cifrado SSL 256-bit</span>
            </div>
            <div class="trust-badge-item">
              ${window.ICONS.shipping}
              <span>Envío Asegurado</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  modalOverlay.classList.add('open');
  document.body.style.overflow = 'hidden';

  // Listeners de Checkout
  document.getElementById('btn-close-checkout').addEventListener('click', closeCheckoutModal);

  // Tabs de pago
  modalContent.querySelectorAll('.payment-tab-btn').forEach(tabBtn => {
    tabBtn.addEventListener('click', () => {
      const tabId = tabBtn.getAttribute('data-tab');
      AppState.activePaymentTab = tabId;

      modalContent.querySelectorAll('.payment-tab-btn').forEach(b => b.classList.remove('active'));
      tabBtn.classList.add('active');

      modalContent.querySelectorAll('.payment-panel').forEach(p => p.classList.remove('active'));
      const activePanel = document.getElementById(`panel-${tabId}`);
      if (activePanel) activePanel.classList.add('active');
    });
  });

  // Botón Mercado Pago
  document.getElementById('btn-pay-mp').addEventListener('click', handleMercadoPagoCheckout);

  // Botón Tarjeta Directa
  document.getElementById('btn-pay-card').addEventListener('click', handleDirectCardCheckout);

  // Botón Transferencia
  document.getElementById('btn-pay-transfer').addEventListener('click', handleTransferCheckout);
}

function closeCheckoutModal() {
  const modalOverlay = document.getElementById('checkout-modal-overlay');
  if (modalOverlay) {
    modalOverlay.classList.remove('open');
    document.body.style.overflow = '';
  }
}

// --- PROCESAMIENTO DE PAGOS CON EL BACKEND ---

async function handleMercadoPagoCheckout() {
  const btn = document.getElementById('btn-pay-mp');
  btn.disabled = true;
  btn.innerHTML = `<span>Conectando con Mercado Pago...</span>`;

  const payload = {
    items: AppState.cart.map(it => ({
      id: it.product.id,
      title: `${it.product.name} (${it.size})`,
      unit_price: it.product.price,
      quantity: it.quantity
    })),
    payer: {
      name: document.getElementById('chk-name').value,
      email: document.getElementById('chk-email').value,
      dni: document.getElementById('chk-dni').value,
      address: document.getElementById('chk-address').value,
      province: document.getElementById('chk-province').value
    }
  };

  try {
    const res = await fetch('/api/checkout/preference', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();

    if (result.success) {
      if (result.init_point && result.mode === 'live') {
        showToast('Redirigiendo a Mercado Pago para abonar de forma segura...');
        clearCart();
        setTimeout(() => {
          window.location.href = result.init_point;
        }, 600);
        return;
      }

      // Mostrar confirmación interactiva
      renderPaymentSuccess({
        type: 'mercadopago',
        order_id: result.order_id,
        preference_id: result.preference_id,
        mode: result.mode,
        init_point: result.init_point,
        message: result.message || 'Preferencia de Mercado Pago lista.',
        total: payload.items.reduce((a, b) => a + (b.unit_price * b.quantity), 0)
      });
      clearCart();
    } else {
      showToast('Error al conectar con Mercado Pago: ' + (result.error || 'intente nuevamente'));
      btn.disabled = false;
      btn.innerHTML = `<span>Continuar con Mercado Pago</span>`;
    }
  } catch (e) {
    console.error(e);
    showToast('Error de conexión con el servidor de pagos');
    btn.disabled = false;
  }
}

async function handleDirectCardCheckout() {
  const btn = document.getElementById('btn-pay-card');
  const cardNum = document.getElementById('card-num').value;
  const cardHolder = document.getElementById('card-holder').value;
  const cardCvv = document.getElementById('card-cvv').value;
  const installments = document.getElementById('card-installments').value;
  const subtotal = AppState.cart.reduce((acc, item) => acc + (item.product.price * item.quantity), 0);

  if (!cardNum || !cardHolder || !cardCvv) {
    showToast('Por favor completá los datos de la tarjeta');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span>Verificando con la red bancaria...</span>`;

  try {
    const res = await fetch('/api/checkout/process-card', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        card_number: cardNum,
        cardholder: cardHolder,
        cvv: cardCvv,
        installments: parseInt(installments),
        total_amount: subtotal,
        dni: document.getElementById('chk-dni').value
      })
    });
    const result = await res.json();

    if (result.success) {
      renderPaymentSuccess({
        type: 'card',
        order_id: result.order_id,
        brand: result.brand,
        last_four: result.last_four,
        auth_code: result.auth_code,
        installments: result.installments,
        installment_amount: result.installment_amount,
        total_paid: result.total_paid,
        date: result.date
      });
      clearCart();
    } else {
      showToast(result.error || 'Tarjeta rechazada');
      btn.disabled = false;
      btn.innerHTML = `<span>Confirmar Pago</span>`;
    }
  } catch (e) {
    showToast('Error procesando el pago con tarjeta');
    btn.disabled = false;
  }
}

async function handleTransferCheckout() {
  const btn = document.getElementById('btn-pay-transfer');
  const subtotal = AppState.cart.reduce((acc, item) => acc + (item.product.price * item.quantity), 0);

  btn.disabled = true;
  btn.innerHTML = `<span>Generando orden con bonificación...</span>`;

  try {
    const res = await fetch('/api/checkout/bank-transfer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        total_amount: subtotal,
        customer_name: document.getElementById('chk-name').value,
        email: document.getElementById('chk-email').value
      })
    });
    const result = await res.json();

    if (result.success) {
      renderPaymentSuccess({
        type: 'transfer',
        order_id: result.order_id,
        original_amount: result.original_amount,
        final_amount: result.final_amount,
        bank_details: result.bank_details,
        instructions: result.instructions
      });
      clearCart();
    }
  } catch (e) {
    showToast('Error generando la orden de transferencia');
    btn.disabled = false;
  }
}

// Pantalla de confirmación de pago
function renderPaymentSuccess(data) {
  const container = document.getElementById('checkout-card-container');
  if (!container) return;

  let detailsHtml = '';

  if (data.type === 'mercadopago') {
    detailsHtml = `
      <div style="background-color: var(--bg-main); border: 1px solid var(--border-light); padding: 1.5rem; border-radius: var(--radius-xs); width: 100%; max-width: 480px; text-align: left; font-size: 0.85rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.6rem;">
          <span style="color: var(--text-muted);">Plataforma de Cobro:</span>
          <strong>Mercado Pago Argentina</strong>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.6rem;">
          <span style="color: var(--text-muted);">Preferencia Generada:</span>
          <code style="background: var(--bg-surface); padding: 0.2rem 0.4rem; border-radius: 2px;">${data.preference_id}</code>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.6rem;">
          <span style="color: var(--text-muted);">Monto Total:</span>
          <strong>${formatARS(data.total)}</strong>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span style="color: var(--text-muted);">Financiación:</span>
          <span style="color: var(--status-success); font-weight: 600;">Hasta 6 Cuotas Bancarias</span>
        </div>
        ${data.init_point ? `
          <div style="margin-top: 1.2rem;">
            <a href="${data.init_point}" class="btn-luxury" style="width: 100%; justify-content: center; text-decoration: none;" id="btn-open-mp-gateway">
              <span>Abrir Pasarela de Pago Mercado Pago</span>
            </a>
          </div>
        ` : ''}
      </div>
    `;
  } else if (data.type === 'card') {
    detailsHtml = `
      <div style="background-color: var(--bg-main); border: 1px solid var(--border-light); padding: 1.5rem; border-radius: var(--radius-xs); width: 100%; max-width: 480px; text-align: left; font-size: 0.85rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.6rem;">
          <span style="color: var(--text-muted);">Medio de Pago:</span>
          <strong>${data.brand} (Terminada en ${data.last_four})</strong>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.6rem;">
          <span style="color: var(--text-muted);">Plan de Financiación:</span>
          <strong style="color: var(--status-success);">${data.installments} cuota${data.installments > 1 ? 's' : ''} de ${formatARS(data.installment_amount)}</strong>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.6rem;">
          <span style="color: var(--text-muted);">Código de Autorización:</span>
          <code>${data.auth_code}</code>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span style="color: var(--text-muted);">Fecha y Hora:</span>
          <span>${data.date}</span>
        </div>
      </div>
    `;
  } else if (data.type === 'transfer') {
    detailsHtml = `
      <div class="bank-transfer-box">
        <div style="font-weight: 700; font-size: 0.9rem; color: var(--gold-dark); margin-bottom: 0.8rem; text-align: center;">
          Datos Bancarios para Transferir (${formatARS(data.final_amount)})
        </div>
        <div class="bank-transfer-row">
          <span>Banco:</span>
          <strong>${data.bank_details.banco}</strong>
        </div>
        <div class="bank-transfer-row">
          <span>Titular:</span>
          <strong>${data.bank_details.titular}</strong>
        </div>
        <div class="bank-transfer-row">
          <span>CUIT:</span>
          <strong>${data.bank_details.cuit}</strong>
        </div>
        <div class="bank-transfer-row">
          <span>Alias CBU:</span>
          <strong id="copy-alias-val" style="color: var(--gold-dark); cursor: pointer;" title="Hacé clic para copiar">${data.bank_details.alias}</strong>
          <span class="btn-copy" onclick="copyToClipboard('${data.bank_details.alias}', 'Alias CBU copiado al portapapeles')">Copiar</span>
        </div>
        <div class="bank-transfer-row">
          <span>CBU Numérico:</span>
          <span style="font-family: monospace;">${data.bank_details.cbu}</span>
          <span class="btn-copy" onclick="copyToClipboard('${data.bank_details.cbu}', 'CBU copiado')">Copiar</span>
        </div>
      </div>
      <p style="font-size: 0.8rem; color: var(--text-secondary); max-width: 480px; line-height: 1.6;">
        ${data.instructions}
      </p>
    `;
  }

  container.innerHTML = `
    <div class="order-confirmation-box">
      <div class="confirmation-icon">
        ${window.ICONS.check}
      </div>

      <span style="font-size: 0.75rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--gold-dark); font-weight: 600;">
        Operación Confirmada
      </span>

      <h2 class="serif-font" style="font-size: 2.4rem; color: var(--text-primary); margin: -0.5rem 0 0.5rem;">
        ¡Gracias por elegir GALILEA Atelier!
      </h2>

      <p style="font-size: 0.9rem; color: var(--text-secondary); max-width: 520px; line-height: 1.6;">
        Tu orden ha sido registrada con el código oficial <strong style="color: var(--text-primary);">${data.order_id}</strong>.
        Te enviamos los detalles y el número de seguimiento asegurado por Andreani a tu casilla de correo.
      </p>

      ${detailsHtml}

      <div style="display: flex; gap: 1rem; margin-top: 1rem;">
        <button class="btn-luxury" onclick="closeCheckoutModal()">
          <span>Volver a la Tienda</span>
        </button>
      </div>
    </div>
  `;
}

function clearCart() {
  AppState.cart = [];
  saveCartToStorage();
  updateCartUI();
}

function copyToClipboard(text, successMsg = 'Copiado al portapapeles') {
  navigator.clipboard.writeText(text).then(() => {
    showToast(successMsg);
  }).catch(() => {
    showToast('Seleccioná el texto para copiarlo');
  });
}

// --- NOTIFICACIONES TOAST ---

function showToast(message) {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <span>${window.ICONS.check}</span>
    <span>${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// --- LISTENERS GLOBALES ---

function setupEventListeners() {
  // Botones de abrir carrito
  document.querySelectorAll('.btn-open-cart').forEach(btn => {
    btn.addEventListener('click', openCartDrawer);
  });

  // Cerrar carrito
  const btnCloseCart = document.getElementById('btn-close-cart');
  if (btnCloseCart) btnCloseCart.addEventListener('click', closeCartDrawer);

  const drawerOverlay = document.getElementById('drawer-overlay');
  if (drawerOverlay) drawerOverlay.addEventListener('click', closeCartDrawer);

  // Botón proceder al Checkout en el drawer
  const btnCheckout = document.getElementById('btn-proceed-checkout');
  if (btnCheckout) btnCheckout.addEventListener('click', openCheckoutModal);

  // Filtro por metal
  const metalSelect = document.getElementById('metal-filter');
  if (metalSelect) {
    metalSelect.addEventListener('change', (e) => {
      AppState.activeMetal = e.target.value;
      fetchProducts();
    });
  }

  // Ordenamiento
  const sortSelect = document.getElementById('sort-order');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      AppState.sortOrder = e.target.value;
      fetchProducts();
    });
  }

  // Búsqueda en Cabecera (Soporte Desktop y Móvil Sincronizado)
  const searchInputDesktop = document.getElementById('header-search-input');
  const searchInputMobile = document.getElementById('header-search-input-mobile');

  function bindSearchInput(inputEl, otherInputEl) {
    if (!inputEl) return;
    let timeout = null;
    inputEl.addEventListener('input', (e) => {
      clearTimeout(timeout);
      const val = e.target.value;
      if (otherInputEl && otherInputEl.value !== val) {
        otherInputEl.value = val;
      }
      timeout = setTimeout(() => {
        AppState.searchQuery = val;
        fetchProducts();
      }, 350);
    });
  }

  bindSearchInput(searchInputDesktop, searchInputMobile);
  bindSearchInput(searchInputMobile, searchInputDesktop);

  // Cerrar modal al cliquear en overlay exterior
  const quickviewOverlay = document.getElementById('quickview-modal-overlay');
  if (quickviewOverlay) {
    quickviewOverlay.addEventListener('click', (e) => {
      if (e.target === quickviewOverlay) closeQuickView();
    });
  }

  const checkoutOverlay = document.getElementById('checkout-modal-overlay');
  if (checkoutOverlay) {
    checkoutOverlay.addEventListener('click', (e) => {
      if (e.target === checkoutOverlay) closeCheckoutModal();
    });
  }

  // Tecla Escape cierra modales y chat
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeQuickView();
      closeCheckoutModal();
      closeCartDrawer();
      const chatWidget = document.getElementById('ai-chat-widget');
      if (chatWidget && chatWidget.classList.contains('is-open')) {
        chatWidget.classList.remove('is-open');
      }
    }
  });

  // Suscripción al newsletter
  const newsletterForm = document.getElementById('newsletter-form');
  if (newsletterForm) {
    newsletterForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('newsletter-email');
      if (input && input.value) {
        showToast('Gracias por suscribirte al atelier');
        input.value = '';
      }
    });
  }
}

// --- ASESORA VIRTUAL DE JOYERÍA CON IA (GALILEA CONCIERGE) ---

function initAIChatAdvisor() {
  const widgetEl = document.getElementById('ai-chat-widget');
  const triggerBtn = document.getElementById('ai-chat-trigger');
  const hintPill = document.getElementById('ai-chat-hint-pill');
  const closeBtn = document.getElementById('ai-chat-close');
  const resetBtn = document.getElementById('ai-chat-reset');
  const soundToggleBtn = document.getElementById('ai-chat-sound-toggle');
  const micBtn = document.getElementById('ai-chat-mic');
  const formEl = document.getElementById('ai-chat-form');
  const inputEl = document.getElementById('ai-chat-input');
  const messagesEl = document.getElementById('ai-chat-messages');

  // Historial de conversación para contexto de IA multi-turno
  const chatHistory = [];
  let isSoundEnabled = localStorage.getItem('galilea_chat_sound') !== 'muted';

  if (!widgetEl || !triggerBtn || !formEl) return;

  // Actualizar estado visual del botón de sonido
  function updateSoundIcon() {
    if (soundToggleBtn) {
      soundToggleBtn.innerHTML = isSoundEnabled ? (window.getIcon ? window.getIcon('volumeUp') : '') : (window.getIcon ? window.getIcon('volumeMute') : '');
      soundToggleBtn.classList.toggle('is-muted', !isSoundEnabled);
      soundToggleBtn.setAttribute('title', isSoundEnabled ? 'Silenciar notificaciones del chat' : 'Activar sonido del chat');
    }
  }
  updateSoundIcon();

  if (soundToggleBtn) {
    soundToggleBtn.addEventListener('click', () => {
      isSoundEnabled = !isSoundEnabled;
      localStorage.setItem('galilea_chat_sound', isSoundEnabled ? 'active' : 'muted');
      updateSoundIcon();
      showToast(isSoundEnabled ? 'Sonido del chat activado' : 'Sonido del chat silenciado');
      if (isSoundEnabled) playChatChime();
    });
  }

  // Micro-chime de audio sutil tipo boutique con Web Audio API
  function playChatChime() {
    if (!isSoundEnabled) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1318.51, ctx.currentTime); // E6
      osc.frequency.exponentialRampToValueAtTime(1661.22, ctx.currentTime + 0.12); // G#6
      gain.gain.setValueAtTime(0.04, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.32);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.32);
    } catch (e) {
      // AudioContext bloqueado o no disponible
    }
  }

  // Dictado por voz (Web Speech API)
  if (micBtn) {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
      const recognition = new SpeechRec();
      recognition.lang = 'es-AR';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        micBtn.classList.add('is-recording');
        micBtn.setAttribute('title', 'Escuchando tu pregunta... (hablá ahora)');
        showToast('Escuchando... dictá tu consulta sobre joyas');
      };

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          inputEl.value = transcript;
          handleUserMessage(transcript);
        }
      };

      recognition.onerror = () => {
        micBtn.classList.remove('is-recording');
        micBtn.setAttribute('title', 'Dictar por voz');
      };

      recognition.onend = () => {
        micBtn.classList.remove('is-recording');
        micBtn.setAttribute('title', 'Dictar por voz');
      };

      micBtn.addEventListener('click', () => {
        try {
          if (micBtn.classList.contains('is-recording')) {
            recognition.stop();
          } else {
            recognition.start();
          }
        } catch (err) {
          micBtn.classList.remove('is-recording');
        }
      });
    } else {
      micBtn.style.display = 'none';
    }
  }

  function toggleChat(forceOpen = null) {
    const shouldOpen = forceOpen !== null ? forceOpen : !widgetEl.classList.contains('is-open');
    if (shouldOpen) {
      widgetEl.classList.add('is-open');
      const windowEl = document.getElementById('ai-chat-window');
      if (windowEl) windowEl.setAttribute('aria-hidden', 'false');
      setTimeout(() => inputEl && inputEl.focus(), 250);
      scrollChatToBottom();
    } else {
      widgetEl.classList.remove('is-open');
      const windowEl = document.getElementById('ai-chat-window');
      if (windowEl) windowEl.setAttribute('aria-hidden', 'true');
    }
  }

  triggerBtn.addEventListener('click', () => toggleChat());
  if (hintPill) hintPill.addEventListener('click', () => toggleChat(true));
  if (closeBtn) closeBtn.addEventListener('click', () => toggleChat(false));

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      messagesEl.innerHTML = `
        <div class="chat-msg bot-msg">
          <div class="msg-bubble">
            ¡Conversación reiniciada! ¿Qué diseño o detalle te gustaría descubrir hoy?
          </div>
          <span class="msg-time">Ahora</span>
        </div>
        <div class="ai-quick-prompts" id="ai-quick-prompts">
          <button type="button" class="quick-prompt-btn" data-query="¿Cómo puedo saber mi talle de anillo?">
            <span data-icon="ruler"></span>
            <span>¿Cómo mido mi talle?</span>
          </button>
          <button type="button" class="quick-prompt-btn" data-query="¿Qué diferencia hay entre oro amarillo 18k y oro blanco?">
            <span data-icon="diamond"></span>
            <span>Oro 18K vs Oro Blanco</span>
          </button>
          <button type="button" class="quick-prompt-btn" data-query="Quiero un anillo de compromiso o regalo especial">
            <span data-icon="gift"></span>
            <span>Anillo de Compromiso</span>
          </button>
          <button type="button" class="quick-prompt-btn" data-query="¿Cómo son los diamantes cultivados en laboratorio?">
            <span data-icon="sparkle"></span>
            <span>Diamantes Lab-Grown</span>
          </button>
          <button type="button" class="quick-prompt-btn" data-query="¿Cómo funcionan las 3 y 6 cuotas y medios de pago?">
            <span data-icon="creditCard"></span>
            <span>Cuotas y Mercado Pago</span>
          </button>
          <button type="button" class="quick-prompt-btn" data-query="¿Cómo funcionan los envíos a todo el país?">
            <span data-icon="shipping"></span>
            <span>Envíos Andreani</span>
          </button>
        </div>
      `;
      chatHistory.length = 0;
      if (window.initIcons) window.initIcons(messagesEl);
      scrollChatToBottom();
      showToast('Conversación reiniciada');
    });
  }

  // Delegación de eventos para las preguntas rápidas (Chips)
  messagesEl.addEventListener('click', (e) => {
    const btn = e.target.closest('.quick-prompt-btn');
    if (btn) {
      const query = btn.getAttribute('data-query');
      if (query) {
        handleUserMessage(query);
      }
    }
  });

  // Envío del formulario de texto
  formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = '';
    handleUserMessage(text);
  });

  function scrollChatToBottom() {
    if (messagesEl) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  function appendUserMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-msg user-msg';
    const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    msgDiv.innerHTML = `
      <div class="msg-bubble">${escapeHTML(text)}</div>
      <span class="msg-time">${nowStr}</span>
    `;
    messagesEl.appendChild(msgDiv);
    scrollChatToBottom();
  }

  // Formateador de Markdown a HTML elegante
  function formatMarkdown(text) {
    if (!text) return '';
    let html = text;
    // Negrita **texto** o __texto__
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');
    // Cursiva *texto* o _texto_
    html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
    // Código `código`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Viñetas: líneas que empiezan con • o - o *
    html = html.replace(/(?:^|\n)[-•*]\s+(.+)/g, '\n<li>$1</li>');
    // Agrupar <li> consecutivos en <ul>
    html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul class="chat-intro-list">$1</ul>');
    // Reemplazar saltos de línea dobles y simples
    html = html.replace(/\n\n+/g, '<br><br>');
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  function appendBotMessage(content, matchedProducts = [], suggestions = []) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-msg bot-msg';
    const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // 1. Tarjetas interactivas de producto con Doble Acción (Ver / Comprar)
    let prodsHtml = '';
    if (matchedProducts && matchedProducts.length > 0) {
      prodsHtml = matchedProducts.slice(0, 3).map(prod => {
        const cuota3 = Math.round(prod.price / 3);
        const metalText = prod.metal ? `<div class="ai-prod-metal-tag">${escapeHTML(prod.metal)}</div>` : '';
        return `
          <div class="ai-prod-recommendation" data-id="${prod.id}">
            <img src="${prod.primary_image}" alt="${escapeHTML(prod.name)}" class="ai-prod-thumb" data-view-id="${prod.id}" title="Ver imagen ampliada">
            <div class="ai-prod-details" data-view-id="${prod.id}">
              <div class="ai-prod-title">${escapeHTML(prod.name)}</div>
              ${metalText}
              <div class="ai-prod-price">${formatARS(prod.price)} <span style="font-size: 0.68rem; font-weight: normal; color: var(--text-muted);">· 3x ${formatARS(cuota3)}</span></div>
            </div>
            <div class="ai-prod-actions">
              <button type="button" class="ai-prod-view-btn" data-view-id="${prod.id}">
                Ver
              </button>
              <button type="button" class="ai-prod-buy-btn" data-add-id="${prod.id}" title="Agregar a la bolsa de compras">
                + Bolsa
              </button>
            </div>
          </div>
        `;
      }).join('');
    }

    // 2. Chips dinámicos contextuales
    let chipsHtml = '';
    if (suggestions && suggestions.length > 0) {
      chipsHtml = `
        <div class="ai-quick-prompts">
          ${suggestions.map(sug => `
            <button type="button" class="quick-prompt-btn" data-query="${escapeHTML(sug)}">
              <span data-icon="sparkle"></span>
              <span>${escapeHTML(sug)}</span>
            </button>
          `).join('')}
        </div>
      `;
    }

    const formattedContent = formatMarkdown(content);

    msgDiv.innerHTML = `
      <div class="msg-bubble">
        ${formattedContent}
        ${prodsHtml}
        ${chipsHtml}
      </div>
      <span class="msg-time">${nowStr}</span>
    `;

    messagesEl.appendChild(msgDiv);
    if (window.initIcons) window.initIcons(msgDiv);
    scrollChatToBottom();
    playChatChime();

    // Eventos: Abrir QuickView
    msgDiv.querySelectorAll('[data-view-id]').forEach(el => {
      el.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const id = el.getAttribute('data-view-id');
        const prod = (AppState.products || []).find(p => p.id === id);
        if (prod) openQuickView(prod);
      });
    });

    // Eventos: Agregar a la bolsa directamente desde el chat
    msgDiv.querySelectorAll('[data-add-id]').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const id = btn.getAttribute('data-add-id');
        const prod = (AppState.products || []).find(p => p.id === id);
        if (prod) {
          addToCart(prod.id, 1, prod.sizes && prod.sizes.length ? prod.sizes[0] : null);
          btn.textContent = '¡Agregada!';
          btn.style.background = '#3E9E68';
          setTimeout(() => {
            btn.textContent = '+ Bolsa';
            btn.style.background = '';
          }, 2000);
        }
      });
    });
  }

  function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-msg bot-msg';
    typingDiv.id = 'ai-typing-indicator';
    typingDiv.innerHTML = `
      <div class="ai-typing-indicator">
        <span class="ai-typing-dot"></span>
        <span class="ai-typing-dot"></span>
        <span class="ai-typing-dot"></span>
      </div>
    `;
    messagesEl.appendChild(typingDiv);
    scrollChatToBottom();
  }

  function removeTypingIndicator() {
    const el = document.getElementById('ai-typing-indicator');
    if (el) el.remove();
  }

  async function handleUserMessage(query) {
    appendUserMessage(query);
    showTypingIndicator();

    chatHistory.push({ role: 'user', text: query });

    let botReply = '';
    let matchedProducts = [];
    let suggestions = [];

    try {
      // 1. Intentar llamar al backend con el historial completo
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: query, history: chatHistory })
      });

      if (res.ok) {
        const data = await res.json();
        if (data && data.success && data.reply) {
          botReply = data.reply;
          matchedProducts = data.products || [];
          suggestions = data.suggestions || [];
        }
      }
    } catch (err) {
      console.warn('Backend chat no disponible, recurriendo al motor de joyería del cliente:', err);
    }

    // 2. Si no hubo respuesta del backend, recurrir al motor experto del cliente
    if (!botReply) {
      await new Promise(r => setTimeout(r, 400));
      const localResponse = generateAIResponse(query);
      botReply = localResponse.text;
      matchedProducts = localResponse.products || [];
      suggestions = localResponse.suggestions || [];
    }

    removeTypingIndicator();
    appendBotMessage(botReply, matchedProducts, suggestions);
    chatHistory.push({ role: 'assistant', text: botReply });
  }

  function escapeHTML(str) {
    if (!str) return '';
    const p = document.createElement('p');
    p.textContent = str;
    return p.innerHTML;
  }
}

// Patrones de detección para temas ajenos a la joyería (Guardrail Estricto)
const OFF_TOPIC_REGEX = /\b(python|javascript|typescript|react|html|css|php|java|c\+\+|sql|codigo|código|programar|programacion|programación|script|bug|api|backend|frontend|futbol|fútbol|messi|maradona|river|boca|partido|mundial|champions|gol|deporte|tenis|nba|politica|política|presidente|elecciones|gobierno|milei|cristina|macri|receta|cocinar|torta|brownie|pasta|asado|horno|matematica|matemática|ecuacion|ecuación|raiz cuadrada|derivada|calcular|cuanto es|clima|pronostico|pronóstico|temperatura|va a llover|chiste|broma|cuento|pelicula|película|serie|netflix|spotify|cancion|canción)\b/i;

const JEWELRY_CONTEXT_WORDS = [
  'joya', 'joyas', 'joyeria', 'anillo', 'anillos', 'solitario', 'solitarios', 'alianza', 'alianzas',
  'collar', 'collares', 'gargantilla', 'gargantillas', 'cadena', 'cadenas', 'dije', 'dijes', 'colgante',
  'aro', 'aros', 'arito', 'aritos', 'argolla', 'argollas', 'criollo', 'criollos',
  'pulsera', 'pulseras', 'brazalete', 'brazaletes', 'riviere', 'esclava',
  'oro', 'plata', 'platino', 'rodio', 'quilate', 'quilates', '18k', '925',
  'diamante', 'diamantes', 'gema', 'gemas', 'piedra', 'piedras', 'brillante', 'brillantes', 'zafiro', 'esmeralda', 'rubi', 'perla', 'perlas',
  'talle', 'talles', 'talla', 'medida', 'medidas', 'medir', 'diametro', 'milimetro', 'mm', 'dedo',
  'precio', 'precios', 'cuanto sale', 'cuanto cuesta', 'costo', 'costos', 'presupuesto', 'barato', 'accesible', 'caro', 'exclusivo',
  'pago', 'pagos', 'cuota', 'cuotas', 'tarjeta', 'tarjetas', 'mercado pago', 'mercadopago', 'transferencia', 'descuento', '15%', 'banco',
  'envio', 'envios', 'andreani', 'tiempo', 'demora', 'entrega', 'despacho', 'retiro',
  'taller', 'atelier', 'alvear', 'galilea', 'direccion', 'donde estan', 'donde queda', 'visitar', 'cita', 'horario', 'local', 'tienda',
  'regalo', 'regalos', 'aniversario', 'compromiso', 'casamiento', 'boda', 'novia', 'mama', 'esposa',
  'limpieza', 'limpiar', 'cuidado', 'mantenimiento', 'garantia', 'certificado', 'autenticidad', 'pulido',
  'personalizado', 'personalizados', 'a medida', 'grabar', 'grabado', 'stock', 'como compro', 'contacto', 'whatsapp',
  'cambio', 'cambios', 'devolucion', 'devoluciones', 'mojar', 'agua', 'circon', 'zirconia', 'catalogo', 'quienes son', 'historia', 'sobre ustedes'
];

function normalizeText(text) {
  if (!text) return '';
  let s = text.toLowerCase().trim();
  const map = {
    'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
    'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u'
  };
  s = s.replace(/[áéíóúüàèìòù]/g, m => map[m] || m);
  s = s.replace(/[¿?¡!():;"',.\-_]/g, ' ');
  return s.replace(/\s+/g, ' ').trim();
}

function isOffTopicJS(rawQuery) {
  const norm = normalizeText(rawQuery);
  if (JEWELRY_CONTEXT_WORDS.some(k => norm.includes(k))) return false;
  if (['hola', 'buen dia', 'buenas tardes', 'buenas noches', 'buenas', 'gracias', 'adios', 'chau', 'que tal', 'como estas', 'de diez', 'genial', 'perfecto'].some(k => norm.includes(k))) return false;
  return OFF_TOPIC_REGEX.test(norm);
}

function extractBudgetJS(rawQuery) {
  const norm = normalizeText(rawQuery).replace(/\./g, '').replace(/,/g, '');
  const matchMil = norm.match(/(\d+)\s*(mil|k)/);
  if (matchMil) return parseInt(matchMil[1], 10) * 1000;
  const matchNum = norm.match(/\$?\s*(\d{4,7})/);
  if (matchNum) return parseInt(matchNum[1], 10);
  return null;
}

function matchProductsJS(rawQuery, products = []) {
  if (!products || products.length === 0) return [];
  const norm = normalizeText(rawQuery);
  const budget = extractBudgetJS(rawQuery);

  if (budget) {
    const budgetProds = products.filter(p => p.price <= budget).sort((a, b) => b.price - a.price);
    if (budgetProds.length > 0) return budgetProds.slice(0, 3);
  }

  if (['aro', 'aros', 'arito', 'aritos', 'argolla', 'argollas', 'criollo', 'criollos'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.category === 'aros');
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['collar', 'collares', 'gargantilla', 'gargantillas', 'cadena', 'cadenas', 'dije', 'dijes', 'colgante'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.category === 'collares');
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['pulsera', 'pulseras', 'brazalete', 'brazaletes', 'riviere', 'esclava'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.category === 'pulseras');
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['compromiso', 'casamiento', 'boda', 'alianza', 'alianzas', 'pedida', 'matrimonio'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.category === 'anillos' || normalizeText(p.name).includes('solitario') || p.badge === 'Alta Joyería');
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['diamante', 'diamantes', 'brillante', 'vvs', 'gema'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.category === 'diamantes' || normalizeText(p.name).includes('diamante') || p.badge === 'Alta Joyería');
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['oro blanco', 'blanco'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.metal && normalizeText(p.metal).includes('blanco'));
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['oro amarillo', 'oro 18k', 'oro'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.metal && normalizeText(p.metal).includes('oro'));
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['plata', '925'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.metal && normalizeText(p.metal).includes('plata'));
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['anillo', 'anillos', 'solitario'].some(k => norm.includes(k))) {
    const matched = products.filter(p => p.category === 'anillos');
    if (matched.length > 0) return matched.slice(0, 3);
  }

  if (['barato', 'economico', 'accesible', 'menor precio'].some(k => norm.includes(k))) {
    const sorted = [...products].sort((a, b) => a.price - b.price);
    return sorted.slice(0, 3);
  }

  if (['exclusivo', 'alta gama', 'alta joyeria', 'mas caro'].some(k => norm.includes(k))) {
    const sorted = [...products].sort((a, b) => b.price - a.price);
    return sorted.slice(0, 3);
  }

  const featured = products.filter(p => p.featured);
  return (featured.length > 0 ? featured : products).slice(0, 3);
}

function generateAIResponse(rawQuery) {
  const norm = normalizeText(rawQuery);
  const products = AppState.products || [];
  const budget = extractBudgetJS(rawQuery);
  const matched = matchProductsJS(rawQuery, products);

  // 1. Guardrail para temas ajenos a la joyería
  if (isOffTopicJS(rawQuery)) {
    return {
      text: `Disculpas, como asesora de **GALILEA Atelier** me dedico exclusivamente a orientarte sobre nuestras piezas de joyería fina, metales nobles, gemología, talles y compras en el atelier.\n\nPodés consultarme sobre anillos, aros, collares, cómo medir tu talle de anillo o nuestras facilidades de pago en cuotas sin interés.`,
      products: [],
      suggestions: ["¿Cómo elijo mi talle de anillo?", "Ver joyas en Oro 18K", "Promociones y Cuotas"]
    };
  }

  // 2. Saludos de cortesía
  if (['hola', 'buen dia', 'buenas tardes', 'buenas noches', 'que tal', 'como estas', 'buenas'].some(k => norm.includes(k)) && norm.split(' ').length <= 4) {
    return {
      text: `¡Hola! Qué gusto saludarte. Te doy una cálida bienvenida a **GALILEA Atelier**.\n\nSoy tu asesora virtual de alta orfebrería y gemología. Puedo orientarte en la elección de piezas según tu estilo o presupuesto, ayudarte a medir tu talle de anillo con exactitud o detallarte nuestras facilidades de pago en hasta **6 cuotas fijas sin interés** y envíos asegurados por Andreani.\n\n¿Te gustaría explorar alguna colección en particular?`,
      products: matched,
      suggestions: ["Ver Anillos y Solitarios", "¿Cómo mido mi talle?", "Joyas en Oro 18K"]
    };
  }

  // 3. Agradecimientos y despedidas
  if (['gracias', 'muchas gracias', 'genial', 'perfecto', 'chau', 'adios', 'hasta luego', 'muy amable', 'de diez', 'excelente'].some(k => norm.includes(k))) {
    return {
      text: `¡Ha sido un verdadero placer asesorarte! Recordá que podés consultarme en cualquier momento o comunicarte directamente con nuestro atelier por WhatsApp si querés coordinar una visita privada o diseñar una joya personalizada.\n\n¡Que tengas una hermosa jornada!`,
      products: [],
      suggestions: ["Ver Catálogo Completo", "WhatsApp del Atelier", "Reiniciar Consulta"]
    };
  }

  // 4. Quiénes son / Sobre la marca / Historia
  if (['quienes son', 'quien sos', 'sobre ustedes', 'marca galilea', 'historia', 'que es galilea'].some(k => norm.includes(k))) {
    return {
      text: `**GALILEA Atelier** es una casa argentina de alta joyería y orfebrería de autor ubicada en Av. Alvear 1850, Ciudad Autónoma de Buenos Aires.\n\n• **Nobleza Material:** Forjamos alianzas, solitarios, gargantillas y pulseras exclusivamente en metales nobles genuinos (Oro 18K y Plata 925 de ley) sin baños ni enchapados superficiales.\n• **Sostenibilidad:** Incorporamos diamantes cultivados en laboratorio (lab-grown) carbono neutro certificados VVS, garantizando la misma pureza y dureza 10 Mohs con impacto ambiental positivo.\n• **Atelier:** Contamos con taller propio para ajustes, grabados láser de precisión y mantenimiento perpetuo.`,
      products: matched,
      suggestions: ["Ver Colección Destacada", "Dónde estamos ubicados", "Hablar con un orfebre"]
    };
  }

  // 5. Ubicación, Atelier Central, Visitas y Horarios
  if (['donde estan', 'donde queda', 'ubicacion', 'direccion', 'local', 'tienda fisica', 'showroom', 'taller', 'visitar', 'cita', 'horario', 'abren', 'puedo ir', 'calle'].some(k => norm.includes(k))) {
    return {
      text: `Nuestro **Atelier Central** se encuentra ubicado en:\n\n• **Dirección:** Av. Alvear 1850, Ciudad Autónoma de Buenos Aires.\n• **Modalidad:** Atención personalizada con cita previa para garantizarte privacidad y asesoramiento mano a mano con un maestro orfebre.\n• **Horarios:** Lunes a Viernes de 10:00 a 19:00 hs | Sábados de 10:00 a 14:00 hs.\n\nSi querés coordinar una cita para probarte alianzas o diseñar una joya a medida, podés pulsar el botón de WhatsApp aquí mismo.`,
      products: [],
      suggestions: ["Coordinar cita por WhatsApp", "Ver piezas en catálogo", "Tiempos de envío"]
    };
  }

  // 6. Garantía, Autenticidad, Calidad y Mantenimiento
  if (['garantia', 'certificado', 'autenticidad', 'original', 'calidad', 'reparar', 'reparacion', 'mantenimiento', 'pulido'].some(k => norm.includes(k))) {
    return {
      text: `En **GALILEA Atelier** respaldamos cada obra con los más altos estándares de orfebrería:\n\n• **Garantía Perpetua:** Avalamos de por vida la nobleza y ley de nuestros metales (Oro 18K y Plata 925).\n• **Certificado de Autenticidad Foliado:** Cada pieza incluye especificación de aleación, gramaje y graduación de gemas.\n• **Primer Ajuste de Talle Bonificado:** Si el anillo no te calza a la perfección, lo ajustamos sin cargo con retiro y entrega asegurada.\n• **Mantenimiento Anual Gratuito:** Disponés de pulido y revisión de engastes sin costo anual de por vida en nuestro atelier.`,
      products: matched,
      suggestions: ["¿Cómo mido mi talle?", "Joyas en Oro 18K", "Consultar por WhatsApp"]
    };
  }

  // 7. Cambios, Devoluciones y Satisfacción
  if (['cambio', 'cambios', 'devolucion', 'devoluciones', 'si no me gusta', 'si no le queda', 'si me equivoque', 'politica de cambio'].some(k => norm.includes(k))) {
    return {
      text: `Comprar en GALILEA es 100% libre de riesgos:\n\n• **Plazo de Cambio:** Disponés de **30 días corridos** desde la recepción de tu joya para solicitar un cambio de modelo o medida.\n• **Primer Ajuste Bonificado:** Si elegiste un anillo y el talle necesita modificación, el primer ajuste es **100% gratuito** con retiro y entrega asegurada a domicilio.\n• **Procedimiento Simple:** Nos contactás por WhatsApp o mail y Andreani retira el paquete asegurado por tu domicilio sin complicaciones.`,
      products: matched,
      suggestions: ["¿Cómo mido mi talle?", "Iniciar una compra", "Hablar con soporte"]
    };
  }

  // 8. Cómo comprar / Proceso de pedido
  if (['como compro', 'como es el proceso', 'pasos para comprar', 'como pago', 'hacer pedido', 'agregar al carrito', 'como hacer la compra', 'como encargar'].some(k => norm.includes(k))) {
    return {
      text: `Comprar en GALILEA es ágil, seguro y transparente:\n\n1. **Elegí tu joya:** Podés verla en detalle con 'Ver' o agregarla directamente a tu compra con **'+ Bolsa'** aquí en el chat.\n2. **Seleccioná tu talle:** En tu bolsa hacé clic en 'Iniciar Pago Seguro'.\n3. **Elegí tu beneficio de pago:** Hasta **6 cuotas fijas sin interés** con tarjetas vía Mercado Pago o **15% OFF directo** por Transferencia Bancaria.\n4. **Envío asegurado:** Lo despachamos gratis a tu domicilio con Andreani y te enviamos el código de seguimiento satelital.`,
      products: matched,
      suggestions: ["Ver Catálogo Completo", "Medios de pago y cuotas", "Hablar con un orfebre"]
    };
  }

  // 9. Contacto humano y WhatsApp
  if (['contacto', 'telefono', 'mail', 'whatsapp', 'humano', 'persona', 'asesor real', 'hablar con alguien', 'numero'].some(k => norm.includes(k))) {
    return {
      text: `Podés ponerte en contacto directo con nuestro equipo de orfebres y asesores a través de:\n\n• **WhatsApp Directo:** [+54 9 11 4050-9988](https://wa.me/5491140509988) (Atención personalizada de lunes a sábados).\n• **Correo Institucional:** atelier@galilea-joyeria.com\n• **Atelier:** Av. Alvear 1850, Ciudad Autónoma de Buenos Aires.\n\nHaciendo clic en el botón de WhatsApp superior podés iniciar una conversación de inmediato con una asesora humana.`,
      products: [],
      suggestions: ["Abrir WhatsApp Oficial", "Ver catálogo de joyas", "Seguir chateando aquí"]
    };
  }

  // 10. Diseños personalizados y grabados
  if (['personalizado', 'personalizados', 'a medida', 'grabar', 'grabado', 'inscripcion', 'disenar', 'a pedido'].some(k => norm.includes(k))) {
    return {
      text: `Realizamos **piezas exclusivas y alianzas a medida** en nuestro taller:\n\n• **Grabado Láser de Alta Precisión:** Bonificado sin costo en todas nuestras alianzas y solitarios (nombres, fechas, iniciales o coordenadas).\n• **Orfebrería a Pedido:** Forjamos alianzas en Oro 18K (amarillo o blanco) con acabados pulido espejo, satinado mate o texturado florentino.\n• **Engastes a Medida:** Asesoramiento para montar diamantes o gemas heredadas con monturas contemporáneas.`,
      products: matchProductsJS('alianzas', products),
      suggestions: ["Cotizar por WhatsApp", "Ver alianzas en catálogo", "¿Cómo medir el talle?"]
    };
  }

  // 11. Consulta explícita sobre cómo medir el talle de anillo
  if (['talle', 'talla', 'como se mi talle', 'como mido', 'medir', 'medida', 'diametro', 'milimetro', 'tabla de talles', 'numero de anillo', 'medir mi dedo', 'tamano de anillo'].some(k => norm.includes(k))) {
    return {
      text: `Para conocer tu talle exacto en Argentina, el método más preciso es medir con regla milimetrada el **diámetro interno** de un anillo que te quede cómodo (sin incluir el borde metálico):\n\n• **16.5 mm** = Talle 12 / 13\n• **17.2 mm** = Talle 14 / 15 *(estándar femenino más frecuente)*\n• **18.0 mm** = Talle 17 / 18\n• **19.0 mm** = Talle 20 / 21\n\n**Tranquilidad Galilea:** Todas nuestras piezas cuentan con el **primer ajuste de talle 100% bonificado sin cargo**, incluyendo retiro y entrega asegurada en tu domicilio.`,
      products: matchProductsJS('anillos', products),
      suggestions: ["Ver anillos en stock", "¿Y si es para regalo sorpresa?", "Consultar por WhatsApp"]
    };
  }

  // 12. Compromiso, Casamiento, Alianzas y Pedidas
  if (['compromiso', 'casamiento', 'boda', 'alianza', 'alianzas', 'pedida', 'proponer', 'matrimonio'].some(k => norm.includes(k))) {
    return {
      text: `Para una propuesta de compromiso o unión matrimonial inolvidable, nuestras obras de alta orfebrería destacan por su solidez eterna:\n\n• **Solitarios de Compromiso:** En Oro 18K macizo con diamantes cultivados lab-grown certificados VVS de brillo excepcional.\n• **Alianzas Matrimoniales:** Diseñadas con perfil *comfort-fit* anatómico para uso diario continuo.\n• **Beneficios Especiales:** Incluyen grabado láser personalizado sin cargo y cambio de talle garantizado.`,
      products: matchProductsJS('compromiso', products),
      suggestions: ["Ver Solitarios de Compromiso", "¿Cómo saber su talle en secreto?", "Hablar con un orfebre"]
    };
  }

  // 13. Diamantes cultivados vs Circones / Zirconia / Sintéticos
  if (['circon', 'zirconia', 'cubic', 'sintetico', 'moissanita', 'falso', 'trucho', 'es real'].some(k => norm.includes(k))) {
    return {
      text: `Existe una diferencia radical entre un circón y un diamante cultivado:\n\n• **Circón o Zirconia:** Es una gema sintética blanda de laboratorio (óxido de circonio) que se desgasta, raya y pierde su brillo o se vuelve lechosa con el roce y el agua en pocos meses.\n• **Diamante Cultivado Galilea:** Es un **diamante auténtico** en su física, química y óptica (100% carbono puro cristalizado con dureza 10 Mohs). Brilla eternamente, no se raya y viene con certificación gemológica oficial.`,
      products: matchProductsJS('diamantes', products),
      suggestions: ["Ver joyas con Diamantes", "Certificación VVS", "Consultar por WhatsApp"]
    };
  }

  // 14. ¿Se pueden mojar? / Ducha / Pileta / Mar
  if (['mojar', 'se puede mojar', 'agua', 'ducha', 'pileta', 'mar', 'bano', 'se arruina'].some(k => norm.includes(k))) {
    return {
      text: `¡Sí! Todas nuestras creaciones de **Oro 18K macizo y Plata 925 de ley** son metales nobles macizos y no enchapados, por lo que **no se pelan ni se despintan con el agua cotidiana ni en la ducha**.\n\n• **Recomendación orfebre:** Para conservar el lustre de pulido espejo como el primer día, aconsejamos retirar las piezas antes de ingresar a piletas con cloro intenso o aplicar fragancias y cremas directamente sobre ellas.\n• **Beneficio perpetuo:** Recordá que tenés **mantenimiento y pulido anual bonificado de por vida** en nuestro atelier.`,
      products: matched,
      suggestions: ["Consejos de limpieza", "Joyas en Oro 18K", "Mantenimiento gratuito"]
    };
  }

  // 15. Colección de AROS
  if (['aro', 'aros', 'arito', 'aritos', 'argolla', 'argollas', 'criollo', 'criollos'].some(k => norm.includes(k))) {
    return {
      text: `Nuestra colección de **Aros de Autor** combina ligereza escultural y porte refinado:\n\n• Criollos y argollas macizas forjadas a mano en **Oro 18K y Plata 925**.\n• Cierres de seguridad reforzados antialérgicos para máximo confort.\n• Terminaciones pulidas a mano con brillo espejo inalterable.\n\nAquí tenés nuestras piezas más destacadas para ver detalles o agregar a tu bolsa:`,
      products: matchProductsJS('aros', products),
      suggestions: ["Aros en Oro 18K", "Aros en Plata 925", "Calcular cuotas sin interés"]
    };
  }

  // 16. Colección de COLLARES y GARGANTILLAS
  if (['collar', 'collares', 'gargantilla', 'gargantillas', 'cadena', 'cadenas', 'dije', 'dijes', 'colgante'].some(k => norm.includes(k))) {
    return {
      text: `Nuestras **Gargantillas y Collares** están concebidos para resaltar sobre la piel con delicadeza atemporal:\n\n• Cadenas forjadas en Oro 18K y Plata 925 con largo regulable (40 a 45 cm) que se adapta a cualquier escote.\n• Solitarios colgantes con diamantes cultivados éticos y engastes a cuatro granos de máxima refracción.\n• Broches de seguridad reforzados tipo marinero u oval pulido.`,
      products: matchProductsJS('collares', products),
      suggestions: ["Gargantillas con Diamante", "Collares en Oro 18K", "Opciones para regalo"]
    };
  }

  // 17. Colección de PULSERAS y RIVIÈRES
  if (['pulsera', 'pulseras', 'brazalete', 'brazaletes', 'riviere', 'esclava'].some(k => norm.includes(k))) {
    return {
      text: `Nuestra línea de **Pulseras y Rivières** encarna el equilibrio entre diseño escultórico y ergonomía diaria:\n\n• **Pulseras Rivière / Tenis:** Engarzadas a mano con diamantes cultivados de brillo continuo y cierre de doble traba de seguridad.\n• **Brazaletes Rígidos & Eslabones:** Forjados en Oro 18K macizo y Plata 925 con acabado satinado o espejo.`,
      products: matchProductsJS('pulseras', products),
      suggestions: ["Pulseras Rivière Diamantes", "Medidas de muñeca", "Pulseras en Oro 18K"]
    };
  }

  // 18. Colección de ANILLOS (cuando preguntan por anillos en general, no talle)
  if (['anillo', 'anillos', 'solitario', 'solitarios'].some(k => norm.includes(k))) {
    return {
      text: `Nuestra selección de **Anillos y Solitarios** abarca desde siluetas contemporáneas hasta piezas de alta orfebrería:\n\n• Forjados en **Oro 18K Amarillo Macizo**, **Oro Blanco con rodio** y **Plata 925 de ley**.\n• Con gemas éticas, diamantes cultivados VVS o siluetas minimalistas puras.\n• Incluyen **primer ajuste de talle sin cargo** para que compres con total tranquilidad.`,
      products: matchProductsJS('anillos', products),
      suggestions: ["¿Cómo mido mi talle?", "Solitarios de Compromiso", "Ver piezas en Oro 18K"]
    };
  }

  // 19. Regalos, Aniversarios y Recomendaciones
  if (['regalo', 'regalos', 'recomendar', 'recomiendame', 'que me recomendas', 'aniversario', 'cumpleanos', 'cumple', 'novia', 'mama', 'esposa', 'especial', 'destacado', 'mas vendido'].some(k => norm.includes(k))) {
    return {
      text: `Para agasajar en una ocasión especial o celebrar un hito trascendental, te recomiendo nuestras piezas de silueta universal:\n\n• **Gargantillas con Diamante Solitario:** Una joya atemporal con largo adaptable que no depende de conocer talles de dedo.\n• **Aros Criollos Clásicos:** Perfectos para uso cotidiano o de noche, en Oro 18K o Plata 925.\n• **Presentación de Obsequio:** Todas nuestras joyas se entregan listas para regalar en un estuche rígido forrado en lino, con lazo de satén y cambio garantizado.`,
      products: matched,
      suggestions: ["Gargantillas para regalo", "Aros atemporales", "¿Cómo viene el packaging?"]
    };
  }

  // 20. Metales Nobles (Oro 18k, Oro Blanco, Plata 925)
  if (['oro', 'plata', 'metal', 'metales', '18k', '925', 'blanco', 'rosa', 'amarillo', 'despinta', 'enchapado', 'macizo', 'rodio'].some(k => norm.includes(k))) {
    return {
      text: `En **GALILEA Atelier** forjamos nuestras piezas exclusivamente en metales nobles macizos de primera ley:\n\n• **Oro 18K Amarillo Macizo (750‰):** Nobleza perpetua. No se despinta, no pierde su brillo ni se desgasta con los años.\n• **Oro Blanco 18K:** Aleación de alta orfebrería con paladio y terminación de rodio electrolítico para un brillo níveo inalterable.\n• **Plata 925 de Ley:** Plata esterlina maciza forjada y pulida artesanalmente con acabado espejo antialérgico.\n\nPrescindimos de baños superficiales perecederos para que cada joya conviva con tu piel de generación en generación.`,
      products: matched,
      suggestions: ["Joyas en Oro 18K", "Joyas en Plata 925", "Garantía perpetua"]
    };
  }

  // 21. Diamantes Cultivados y Gemología Ética
  if (['diamante', 'diamantes', 'lab grown', 'cultivado', 'cultivados', 'laboratorio', 'vvs', 'brillante', 'gema', 'gemas', 'piedra', 'zafiro', 'esmeralda', 'rubi'].some(k => norm.includes(k))) {
    return {
      text: `Nuestros diamantes son **cultivados en laboratorio con huella de carbono neutra certificada**:\n\n• **Identidad Absoluta:** Tienen exactamente la misma composición química (100% carbono puro cristalizado en red cúbica), dureza 10 Mohs y brillo óptico que un diamante de mina.\n• **Pureza Superior:** Seleccionamos graduaciones **VVS1 / VVS2** y escala de color **F-G (incoloro excepcional)**.\n• **Sostenibilidad:** Libres de conflicto ético y con trazabilidad verificable certificada.`,
      products: matchProductsJS('diamantes', products),
      suggestions: ["Ver Alta Joyería Diamantes", "¿Tienen certificación oficial?", "Cuotas sin interés"]
    };
  }

  // 22. Descuentos, Promociones y Ofertas
  if (['descuento', 'descuentos', 'promocion', 'promociones', 'promo', 'promos', 'oferta', 'ofertas', 'cupon', '15%'].some(k => norm.includes(k))) {
    return {
      text: `En **GALILEA Atelier** disponemos de importantes beneficios comerciales vigentes:\n\n• **15% de Descuento Inmediato** abonando mediante Transferencia Bancaria directa (Alias: \`GALILEA.JOYAS.ARG\`).\n• **3 y 6 Cuotas Fijas Sin Interés** con tarjetas de crédito bancarias Visa, Mastercard y American Express por Mercado Pago.\n• **Envío Gratis Asegurado** a todo el país a través de Andreani Custodia Express.`,
      products: matched,
      suggestions: ["Datos de Transferencia 15% OFF", "Calcular cuotas", "Ver catálogo de joyas"]
    };
  }

  // 23. Stock y Disponibilidad Inmediata
  if (['stock', 'disponible', 'disponibilidad', 'inmediata', 'entrega inmediata'].some(k => norm.includes(k))) {
    return {
      text: `Todas las piezas expuestas en nuestro catálogo online cuentan con **stock asegurado para despacho prioritario**:\n\n• **CABA y Gran Buenos Aires:** Despacho prioritario en 24 a 48 hs hábiles.\n• **Resto del país:** 3 a 5 días hábiles a domicilio o sucursal Andreani con seguimiento satelital.\n• **Piezas a Medida / Ajustes especiales:** La calibración orfebre toma entre 48 y 72 hs hábiles adicionales.`,
      products: matched,
      suggestions: ["Ver joyas en stock", "¿Cómo mido mi talle?", "Tiempos de envío Andreani"]
    };
  }

  // 24. Precios, Presupuesto y Opciones Accesibles / Exclusivas
  if (budget || ['precio', 'precios', 'cuanto sale', 'cuanto cuesta', 'costo', 'costos', 'presupuesto', 'barato', 'economico', 'accesible', 'caro', 'exclusivo'].some(k => norm.includes(k))) {
    const budgetStr = budget ? ` de hasta **${formatARS(budget)}**` : '';
    return {
      text: `Para tu consulta de presupuesto${budgetStr}, seleccioné creaciones destacadas forjadas en metales nobles:\n\n• **Piezas en Plata 925 de Ley:** Desde $58.000 a $95.000 (o 3 cuotas fijas sin interés de ~$19.000).\n• **Orfebrería en Oro 18K Macizo:** Desde $190.000 a $380.000.\n• **Alta Joyería en Diamantes Cultivados:** Obras de autor de $390.000 a $780.000.\n\nRecordá que abonando por **Transferencia Bancaria tenés un 15% de descuento inmediato**, o podés financiar en **hasta 6 cuotas sin interés**.`,
      products: matched,
      suggestions: ["Opciones más accesibles", "Joyas en Oro 18K", "Calcular cuotas sin interés"]
    };
  }

  // 25. Medios de Pago, Cuotas y Transferencia
  if (['pago', 'pagos', 'cuota', 'cuotas', 'tarjeta', 'tarjetas', 'mercado pago', 'mercadopago', 'transferencia', 'banco', 'alias', 'cbu'].some(k => norm.includes(k))) {
    return {
      text: `Contamos con los siguientes beneficios comerciales en toda la Argentina:\n\n• **3 y 6 Cuotas Fijas Sin Interés** con todas las tarjetas de crédito bancarias (Visa, Mastercard, Amex) procesadas por **Mercado Pago**.\n• **15% de Descuento Inmediato** abonando por Transferencia Bancaria directa (Alias: \`GALILEA.JOYAS.ARG\`).\n• Facturación formal automática tipo A o B y protección de cobro bancario SSL de 256 bits.`,
      products: matched,
      suggestions: ["Datos para Transferencia", "¿Cómo es el envío Andreani?", "Ver catálogo completo"]
    };
  }

  // 26. Envíos y Tiempos de Entrega
  if (['envio', 'envios', 'andreani', 'tiempo', 'demora', 'llega', 'domicilio', 'sucursal', 'interior', 'packaging', 'caja', 'estuche'].some(k => norm.includes(k))) {
    return {
      text: `Brindamos **Envío Gratis Asegurado a toda la República Argentina** a través de **Andreani Custodia Express**:\n\n• **CABA y Gran Buenos Aires:** Despacho prioritario en 24 a 48 hs hábiles.\n• **Resto del país:** 3 a 5 días hábiles a domicilio o sucursal Andreani con seguimiento satelital en tiempo real.\n• **Packaging de Gala:** Cada alhaja viaja en un cofre rígido forrado en lino italiano, lazo de satén, estuche de gamuza y certificado oficial.`,
      products: [],
      suggestions: ["¿El envío tiene seguro total?", "¿Cómo viene el packaging?", "Ver catálogo de joyas"]
    };
  }

  // 27. Catálogo General y Colecciones
  if (['catalogo', 'coleccion', 'colecciones', 'que tienen', 'productos', 'piezas', 'modelos', 'ver todo'].some(k => norm.includes(k))) {
    return {
      text: `En **GALILEA Atelier** forjamos cuatro grandes colecciones de autor:\n\n• **Anillos & Solitarios:** Diseños en Oro 18K y Plata 925 con diamantes cultivados o siluetas puras.\n• **Gargantillas & Collares:** Cadenas de eslabón fino y solitarios colgantes regulables.\n• **Aros Criollos:** Argollas macizas con cierres antialérgicos reforzados.\n• **Pulseras & Rivières:** Brazaletes rígidos y líneas rivière con engaste continuo.\n\nAquí tenés algunas de nuestras piezas más aclamadas para inspeccionar o sumar a tu bolsa:`,
      products: matched,
      suggestions: ["Ver Anillos y Solitarios", "Ver Aros Criollos", "Gargantillas y Collares"]
    };
  }

  // 28. Respuesta conversacional amplia y acogedora (evita insistencias rígidas)
  return {
    text: `Con mucho gusto te asesoro. En **GALILEA Atelier** nos especializamos en alta orfebrería de autor forjada en Buenos Aires:\n\n• **Anillos, Solitarios y Alianzas** en Oro 18K macizo y Plata 925 de ley.\n• **Gargantillas, Aros criollos y Pulseras** con diamantes cultivados éticos.\n• **Medición y primer ajuste de talle 100% bonificado** en todo el país.\n• **Hasta 6 cuotas fijas sin interés** con tarjetas y 15% OFF por transferencia bancaria.\n\nPodés elegir alguna de las sugerencias rápidas debajo o consultarme sobre cualquier pieza, metal o detalle de compra.`,
    products: matched,
    suggestions: ["Ver Anillos y Solitarios", "¿Cómo mido mi talle?", "Joyas en Oro 18K"]
  };
}

// Exponer funciones necesarias al scope global
window.updateCartQuantity = updateCartQuantity;
window.removeCartItem = removeCartItem;
window.copyToClipboard = copyToClipboard;
window.closeCheckoutModal = closeCheckoutModal;
window.selectNavCategory = selectNavCategory;
window.initAIChatAdvisor = initAIChatAdvisor;
