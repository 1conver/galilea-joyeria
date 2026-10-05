/**
 * GALILEA ATELIER - Panel Modular de Gestión (/admin)
 * Control de Acceso, Roles (Operario vs Admin), Catálogo, Ofertas y Logística
 */

const AdminState = {
  token: localStorage.getItem('galilea_admin_token') || '',
  currentUser: null,
  activeModule: 'orders',
  orders: [],
  products: [],
  users: [],
  settings: null,
  stats: null,
  filterStatus: 'all',
  filterShipping: 'all',
  filterMethod: 'all',
  searchQuery: ''
};

const formatARS = (amount) => {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0
  }).format(amount);
};

document.addEventListener('DOMContentLoaded', () => {
  checkAuth();
  setupAuthForm();
});

// --- AUTENTICACIÓN Y SESIÓN ---

async function checkAuth() {
  if (!AdminState.token) {
    showLoginView();
    return;
  }

  try {
    const res = await fetch('/api/auth/me', {
      headers: { 'Authorization': `Bearer ${AdminState.token}` }
    });
    const data = await res.json();

    if (data.success && data.user) {
      AdminState.currentUser = data.user;
      showDashboardView();
      initDashboard();
    } else {
      logout();
    }
  } catch (err) {
    console.error('Error de sesión:', err);
    showLoginView();
  }
}

function showLoginView() {
  document.getElementById('login-view').style.display = 'flex';
  document.getElementById('dashboard-view').style.display = 'none';
  const emailInput = document.getElementById('login-email');
  const passInput = document.getElementById('login-password');
  if (emailInput) emailInput.value = '';
  if (passInput) passInput.value = '';
}

function showDashboardView() {
  document.getElementById('login-view').style.display = 'none';
  document.getElementById('dashboard-view').style.display = 'block';

  // Mostrar datos del usuario en la barra
  const user = AdminState.currentUser;
  const nameEl = document.getElementById('header-user-name');
  const roleBadge = document.getElementById('header-role-badge');

  if (nameEl) nameEl.textContent = user.name;
  if (roleBadge) {
    roleBadge.textContent = user.role === 'admin' ? 'Administrador' : 'Operario de Taller';
    roleBadge.className = `user-role-badge ${user.role === 'admin' ? 'role-admin' : 'role-operario'}`;
  }

  // Filtrar pestañas según el rol
  const adminTabs = document.querySelectorAll('.admin-only-tab');
  if (user.role !== 'admin') {
    adminTabs.forEach(tab => tab.style.display = 'none');
  } else {
    adminTabs.forEach(tab => tab.style.display = 'inline-flex');
  }
}

function setupAuthForm() {
  const form = document.getElementById('admin-login-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('login-email').value;
      const password = document.getElementById('login-password').value;
      const btn = document.getElementById('btn-submit-login');

      btn.disabled = true;
      btn.innerHTML = `<span>Verificando credenciales...</span>`;

      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        const data = await res.json();

        if (data.success && data.token) {
          AdminState.token = data.token;
          AdminState.currentUser = data.user;
          localStorage.setItem('galilea_admin_token', data.token);
          showToast(`Bienvenido al Atelier, ${data.user.name}`);
          showDashboardView();
          initDashboard();
        } else {
          showToast(data.error || 'Credenciales incorrectas');
        }
      } catch (err) {
        showToast('Error de conexión con el servidor');
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Ingresar al Sistema</span>`;
      }
    });
  }
}

function fillLogin(email, password) {
  document.getElementById('login-email').value = email;
  document.getElementById('login-password').value = password;
}

function logout() {
  AdminState.token = '';
  AdminState.currentUser = null;
  localStorage.removeItem('galilea_admin_token');
  showLoginView();
}

// --- SWITCH MODULAR DE PESTAÑAS ---

function switchModule(moduleName) {
  AdminState.activeModule = moduleName;

  // Actualizar botones de pestañas
  document.querySelectorAll('.admin-tab-btn').forEach(b => {
    b.classList.toggle('active', b.getAttribute('data-tab') === moduleName);
  });

  // Ocultar todas las secciones
  document.querySelectorAll('.admin-section-view').forEach(s => s.style.display = 'none');

  // Mostrar la activa
  const activeSec = document.getElementById(`module-${moduleName}`);
  if (activeSec) activeSec.style.display = 'block';

  // Cargar datos correspondientes
  if (moduleName === 'orders') {
    fetchStats();
    fetchOrders();
  } else if (moduleName === 'catalog') {
    fetchCatalog();
  } else if (moduleName === 'marketing') {
    fetchSettings();
  } else if (moduleName === 'team') {
    fetchTeam();
  }
}

// Inicializar datos del dashboard
async function initDashboard() {
  setupFilterListeners();
  setupSettingsForm();
  setupUserCreationForm();
  switchModule('orders');
}

// =========================================================================
// MÓDULO 1: TALLER & DESPACHOS
// =========================================================================

async function fetchStats() {
  try {
    const res = await fetch('/api/admin/stats');
    const data = await res.json();
    if (data.success) {
      AdminState.stats = data.stats;
      renderKPIs();
    }
  } catch (err) {
    console.error(err);
  }
}

function renderKPIs() {
  if (!AdminState.stats) return;
  const s = AdminState.stats;
  document.getElementById('kpi-revenue').textContent = formatARS(s.total_revenue_ars);
  document.getElementById('kpi-pending-transfers').textContent = s.pending_transfers;
  document.getElementById('kpi-workshop').textContent = s.in_workshop;
  document.getElementById('kpi-transit').textContent = s.in_transit;
}

async function fetchOrders() {
  try {
    const url = new URL('/api/admin/orders', window.location.origin);
    if (AdminState.filterStatus !== 'all') url.searchParams.set('status', AdminState.filterStatus);
    if (AdminState.filterShipping !== 'all') url.searchParams.set('shipping', AdminState.filterShipping);
    if (AdminState.filterMethod !== 'all') url.searchParams.set('method', AdminState.filterMethod);
    if (AdminState.searchQuery) url.searchParams.set('q', AdminState.searchQuery);

    const res = await fetch(url);
    const data = await res.json();
    if (data.success) {
      AdminState.orders = data.orders;
      renderOrdersTable();
    }
  } catch (err) {
    console.error(err);
  }
}

function renderOrdersTable() {
  const tbody = document.getElementById('orders-table-body');
  const countEl = document.getElementById('orders-total-count');
  if (countEl) countEl.textContent = `${AdminState.orders.length} pedidos`;
  if (!tbody) return;

  if (AdminState.orders.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
          No se encontraron pedidos con esos filtros.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = AdminState.orders.map(order => {
    let payBadgeClass = order.payment_status === 'approved' ? 'badge-approved' : (order.payment_status === 'rejected' ? 'badge-rejected' : 'badge-pending');
    let shipBadgeClass = order.shipping_status === 'in_workshop' ? 'badge-workshop' : (order.shipping_status === 'in_transit' ? 'badge-transit' : (order.shipping_status === 'delivered' ? 'badge-delivered' : 'badge-pending'));

    const itemsSummary = order.items.map(it => `${it.quantity}x ${it.name} (${it.size})`).join('<br>');

    let actionButtons = `
      <button class="btn-op-action" onclick="openOrderDetailModal('${order.id}')" title="Ver Remito y Contacto">
        ${window.ICONS.eye}
        <span>Detalle</span>
      </button>
    `;

    if (order.payment_status === 'pending_verification') {
      actionButtons += `
        <button class="btn-op-action btn-op-success" onclick="quickApproveTransfer('${order.id}')" title="Validar CBU">
          ${window.ICONS.check}
          <span>Validar CBU</span>
        </button>
      `;
    }

    if (order.payment_status === 'approved' && order.shipping_status === 'in_workshop') {
      actionButtons += `
        <button class="btn-op-action" onclick="openDispatchModal('${order.id}')" title="Asignar Guía Andreani">
          ${window.ICONS.shipping}
          <span>Despachar</span>
        </button>
      `;
    }

    if (order.shipping_status === 'in_transit') {
      actionButtons += `
        <button class="btn-op-action" onclick="markAsDelivered('${order.id}')" title="Marcar Entregado">
          ${window.ICONS.check}
          <span>Entregado</span>
        </button>
      `;
    }

    return `
      <tr>
        <td>
          <span class="order-code-badge">${order.id}</span>
          <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">${order.date}</div>
        </td>
        <td>
          <div style="font-weight: 600;">${order.customer.name}</div>
          <div style="font-size: 0.72rem; color: var(--text-secondary);">DNI: ${order.customer.dni} · ${order.customer.province}</div>
        </td>
        <td>
          <div style="font-size: 0.78rem; line-height: 1.4;">${itemsSummary}</div>
        </td>
        <td>
          <div style="font-weight: 700;">${formatARS(order.total_amount)}</div>
          <div style="font-size: 0.7rem; color: var(--text-muted);">${order.payment_method_label}</div>
        </td>
        <td>
          <span class="badge-status ${payBadgeClass}">
            <span>${order.payment_status_label}</span>
          </span>
        </td>
        <td>
          <span class="badge-status ${shipBadgeClass}">
            <span>${order.shipping_status_label}</span>
          </span>
          ${order.tracking_number ? `<div style="font-size: 0.7rem; font-family: monospace; color: var(--gold-dark); margin-top: 0.2rem;">Guía: ${order.tracking_number}</div>` : ''}
        </td>
        <td>
          <div class="table-action-btns">${actionButtons}</div>
        </td>
      </tr>
    `;
  }).join('');
}

async function quickApproveTransfer(orderId) {
  if (!confirm(`¿Confirmás la acreditación bancaria para el pedido ${orderId}?`)) return;
  try {
    const res = await fetch(`/api/admin/orders/${orderId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payment_status: 'approved', shipping_status: 'in_workshop' })
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Pedido ${orderId} acreditado. Derivado a taller.`);
      await fetchStats();
      await fetchOrders();
    }
  } catch (err) {
    showToast('Error al confirmar cobro');
  }
}

function openDispatchModal(orderId) {
  const suggestedGuide = `ANDR-${Math.floor(100000000 + Math.random() * 900000000)}AR`;
  const tracking = prompt(`Ingresá el número de guía Andreani para ${orderId}:`, suggestedGuide);
  if (tracking && tracking.trim()) {
    dispatchOrder(orderId, tracking.trim());
  }
}

async function dispatchOrder(orderId, trackingNumber) {
  try {
    const res = await fetch(`/api/admin/orders/${orderId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shipping_status: 'in_transit', tracking_number: trackingNumber })
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Pedido ${orderId} despachado.`);
      await fetchStats();
      await fetchOrders();
    }
  } catch (err) {
    showToast('Error al despachar');
  }
}

async function markAsDelivered(orderId) {
  if (!confirm(`¿Marcar ${orderId} como entregado?`)) return;
  try {
    const res = await fetch(`/api/admin/orders/${orderId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shipping_status: 'delivered' })
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Pedido ${orderId} marcado como entregado.`);
      await fetchStats();
      await fetchOrders();
    }
  } catch (err) {
    showToast('Error al actualizar');
  }
}

function openOrderDetailModal(orderId) {
  const order = AdminState.orders.find(o => o.id === orderId);
  if (!order) return;

  const overlay = document.getElementById('admin-modal-overlay');
  const container = document.getElementById('admin-modal-content');
  const cleanPhone = order.customer.phone.replace(/[^0-9]/g, '');
  const whatsappUrl = `https://wa.me/${cleanPhone}?text=${encodeURIComponent(`Hola ${order.customer.name}, te contactamos de GALILEA Atelier sobre tu orden ${order.id}.`)}`;

  container.innerHTML = `
    <div class="admin-modal-card">
      <button class="btn-close-modal" onclick="closeAdminModal()">${window.ICONS.close}</button>
      <div class="admin-order-head">
        <div>
          <span style="font-size: 0.72rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--gold-dark); font-weight: 600;">Remito de Orfebrería</span>
          <h2 class="serif-font" style="font-size: 2.2rem; color: var(--text-primary); margin: 0.2rem 0;">Pedido ${order.id}</h2>
          <div style="font-size: 0.8rem; color: var(--text-muted);">${order.date}</div>
        </div>
        <div style="text-align: right;">
          <div style="font-size: 1.5rem; font-weight: 700;">${formatARS(order.total_amount)}</div>
          <div style="font-size: 0.75rem; color: var(--status-success); font-weight: 600;">${order.payment_method_label}</div>
        </div>
      </div>

      <div class="client-contact-card">
        <div>
          <strong style="color: var(--gold-dark); text-transform: uppercase; font-size: 0.72rem;">Datos del Comprador</strong>
          <div><strong>Nombre:</strong> ${order.customer.name}</div>
          <div><strong>DNI / CUIL:</strong> ${order.customer.dni}</div>
          <div><strong>Teléfono:</strong> ${order.customer.phone}</div>
          <a href="${whatsappUrl}" target="_blank" rel="noopener" class="whatsapp-link-btn">Contactar por WhatsApp</a>
        </div>
        <div>
          <strong style="color: var(--gold-dark); text-transform: uppercase; font-size: 0.72rem;">Destino de Envío</strong>
          <div><strong>Dirección:</strong> ${order.customer.address}</div>
          <div><strong>Provincia:</strong> ${order.customer.province}</div>
          <div><strong>Transporte:</strong> ${order.shipping_carrier}</div>
          ${order.tracking_number ? `<div style="color: var(--gold-dark); font-weight: 700;">Guía: ${order.tracking_number}</div>` : ''}
        </div>
      </div>

      <div style="margin-bottom: 1.8rem;">
        <h4 style="font-size: 0.82rem; text-transform: uppercase; margin-bottom: 0.8rem;">Piezas en Taller</h4>
        <div style="display: flex; flex-direction: column; gap: 0.8rem;">
          ${order.items.map(it => `
            <div style="display: grid; grid-template-columns: 65px 1fr auto; gap: 1rem; align-items: center; padding: 0.8rem; background-color: var(--bg-main); border: 1px solid var(--border-light);">
              <img src="${it.image}" alt="${it.name}" style="width: 65px; height: 65px; object-fit: cover;">
              <div>
                <strong>${it.name}</strong>
                <div style="font-size: 0.75rem; color: var(--gold-dark); font-weight: 600;">Medida Solicitada: ${it.size}</div>
                <div style="font-size: 0.72rem; color: var(--text-muted);">${it.metal}</div>
              </div>
              <div style="text-align: right; font-weight: 600;">${formatARS(it.price * it.quantity)}</div>
            </div>
          `).join('')}
        </div>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center;">
        <button class="btn-luxury-outline" onclick="window.print()">Imprimir Remito Oficial</button>
      </div>
    </div>
  `;
  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeAdminModal() {
  const overlay = document.getElementById('admin-modal-overlay');
  if (overlay) {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }
}

// =========================================================================
// MÓDULO 2: CATÁLOGO & PRECIOS (SOLO ADMIN)
// =========================================================================

async function fetchCatalog() {
  try {
    const res = await fetch('/api/products');
    const data = await res.json();
    if (data.success) {
      AdminState.products = data.products;
      renderCatalogTable();
    }
  } catch (err) {
    console.error(err);
  }
}

function renderCatalogTable() {
  const tbody = document.getElementById('catalog-table-body');
  if (!tbody) return;

  tbody.innerHTML = AdminState.products.map(prod => `
    <tr>
      <td>
        <div style="display: flex; align-items: center; gap: 1rem;">
          <img src="${prod.primary_image}" alt="${prod.name}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 2px;">
          <div>
            <strong style="display: block; font-size: 0.95rem;">${prod.name}</strong>
            <span style="font-size: 0.72rem; color: var(--gold-dark);">${prod.badge || ''}</span>
          </div>
        </div>
      </td>
      <td>
        <div>${prod.category_label}</div>
        <div style="font-size: 0.72rem; color: var(--text-muted);">${prod.metal}</div>
      </td>
      <td>
        <div style="display: flex; align-items: center; gap: 0.4rem;">
          <input type="number" id="price-input-${prod.id}" value="${prod.price}" class="form-input" style="width: 130px; padding: 0.35rem 0.5rem; font-size: 0.85rem; font-weight: 600;">
          <button class="btn-op-action" onclick="saveProductPrice('${prod.id}')" title="Guardar Precio">Guardar</button>
        </div>
      </td>
      <td>
        <button class="btn-op-action ${prod.in_stock ? 'btn-op-success' : ''}" onclick="toggleProductStock('${prod.id}', ${!prod.in_stock})">
          <span>${prod.in_stock ? 'En Stock' : 'Agotado'}</span>
        </button>
      </td>
      <td>
        <span style="font-size: 0.75rem; color: var(--text-muted);">ID: ${prod.id}</span>
      </td>
    </tr>
  `).join('');
}

async function saveProductPrice(id) {
  const input = document.getElementById(`price-input-${id}`);
  if (!input) return;
  const newPrice = parseFloat(input.value);

  try {
    const res = await fetch(`/api/admin/products/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AdminState.token}`
      },
      body: JSON.stringify({ price: newPrice })
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Precio actualizado a ${formatARS(newPrice)}`);
    } else {
      showToast(result.error || 'Error al actualizar precio');
    }
  } catch (e) {
    showToast('Error de conexión');
  }
}

async function toggleProductStock(id, inStock) {
  try {
    const res = await fetch(`/api/admin/products/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AdminState.token}`
      },
      body: JSON.stringify({ in_stock: inStock })
    });
    const result = await res.json();
    if (result.success) {
      showToast(inStock ? 'Pieza marcada En Stock' : 'Pieza marcada Agotada');
      fetchCatalog();
    }
  } catch (e) {
    showToast('Error al actualizar disponibilidad');
  }
}

function openCreateProductModal() {
  const overlay = document.getElementById('admin-modal-overlay');
  const container = document.getElementById('admin-modal-content');

  container.innerHTML = `
    <div class="admin-modal-card" style="max-width: 600px;">
      <button class="btn-close-modal" onclick="closeAdminModal()">${window.ICONS.close}</button>
      <h2 class="serif-font" style="font-size: 2rem; margin-bottom: 1.5rem;">Dar de Alta Nueva Joya</h2>

      <form id="create-product-form" onsubmit="handleCreateProductSubmit(event)">
        <div class="form-group" style="margin-bottom: 1rem;">
          <label class="form-label">Nombre de la Pieza</label>
          <input type="text" id="new-prod-name" class="form-input" placeholder="Ej. Anillo Solitario Alvear" required>
        </div>

        <div class="form-row" style="margin-bottom: 1rem;">
          <div class="form-group">
            <label class="form-label">Categoría</label>
            <select id="new-prod-category" class="form-select">
              <option value="anillos">Anillos</option>
              <option value="collares">Collares</option>
              <option value="aros">Aros</option>
              <option value="pulseras">Pulseras</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Metal Noble</label>
            <select id="new-prod-metal" class="form-select">
              <option value="Oro 18K">Oro 18K Amarillo</option>
              <option value="Oro Blanco 18K">Oro Blanco 18K</option>
              <option value="Plata 925">Plata 925</option>
            </select>
          </div>
        </div>

        <div class="form-row" style="margin-bottom: 1rem;">
          <div class="form-group">
            <label class="form-label">Precio en ARS ($)</label>
            <input type="number" id="new-prod-price" class="form-input" placeholder="Ej. 350000" required>
          </div>
          <div class="form-group">
            <label class="form-label">Etiqueta / Badge</label>
            <input type="text" id="new-prod-badge" class="form-input" placeholder="Ej. Edición Limitada">
          </div>
        </div>

        <div class="form-group" style="margin-bottom: 1rem;">
          <label class="form-label">URL de Fotografía Principal</label>
          <input type="url" id="new-prod-img" class="form-input" placeholder="https://images.unsplash.com/..." required value="https://images.unsplash.com/photo-1605100804763-247f67b3557e?auto=format&fit=crop&w=900&q=85">
        </div>

        <div class="form-group" style="margin-bottom: 1.5rem;">
          <label class="form-label">Descripción Editorial</label>
          <textarea id="new-prod-desc" class="form-input" rows="3" placeholder="Detalles de manufactura artesanal..."></textarea>
        </div>

        <button type="submit" class="btn-luxury" style="width: 100%;">
          <span>Incorporar al Catálogo</span>
        </button>
      </form>
    </div>
  `;
  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
}

async function handleCreateProductSubmit(e) {
  e.preventDefault();
  const name = document.getElementById('new-prod-name').value;
  const category = document.getElementById('new-prod-category').value;
  const metal = document.getElementById('new-prod-metal').value;
  const price = parseFloat(document.getElementById('new-prod-price').value);
  const badge = document.getElementById('new-prod-badge').value;
  const primary_image = document.getElementById('new-prod-img').value;
  const description = document.getElementById('new-prod-desc').value;

  try {
    const res = await fetch('/api/admin/products', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AdminState.token}`
      },
      body: JSON.stringify({ name, category, metal, price, badge, primary_image, description })
    });
    const result = await res.json();
    if (result.success) {
      showToast('Joya incorporada exitosamente');
      closeAdminModal();
      fetchCatalog();
    } else {
      showToast(result.error || 'Error al incorporar pieza');
    }
  } catch (err) {
    showToast('Error de conexión');
  }
}

// =========================================================================
// MÓDULO 3: OFERTAS & TEXTOS DE PORTADA (SOLO ADMIN)
// =========================================================================

async function fetchSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (data.success && data.settings) {
      AdminState.settings = data.settings;
      const s = data.settings;
      document.getElementById('set-ticker').value = s.ticker_text || '';
      document.getElementById('set-hero-tag').value = s.hero_tag || '';
      document.getElementById('set-discount').value = s.transfer_discount_pct || 15;
      document.getElementById('set-hero-title').value = s.hero_title || '';
      document.getElementById('set-hero-desc').value = s.hero_desc || '';
    }
  } catch (e) {
    console.error(e);
  }
}

function setupSettingsForm() {
  const form = document.getElementById('store-settings-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        ticker_text: document.getElementById('set-ticker').value,
        hero_tag: document.getElementById('set-hero-tag').value,
        transfer_discount_pct: parseInt(document.getElementById('set-discount').value),
        hero_title: document.getElementById('set-hero-title').value,
        hero_desc: document.getElementById('set-hero-desc').value
      };

      try {
        const res = await fetch('/api/admin/settings', {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${AdminState.token}`
          },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.success) {
          showToast('Textos y ofertas actualizados en la tienda');
        } else {
          showToast(result.error || 'Error guardando ajustes');
        }
      } catch (err) {
        showToast('Error al conectar con la API');
      }
    });
  }
}

// =========================================================================
// MÓDULO 4: GESTIÓN DE EQUIPO & OPERARIOS (SOLO ADMIN)
// =========================================================================

async function fetchTeam() {
  try {
    const res = await fetch('/api/admin/users', {
      headers: { 'Authorization': `Bearer ${AdminState.token}` }
    });
    const data = await res.json();
    if (data.success) {
      AdminState.users = data.users;
      renderTeamTable();
    }
  } catch (err) {
    console.error(err);
  }
}

function renderTeamTable() {
  const tbody = document.getElementById('team-table-body');
  if (!tbody) return;

  tbody.innerHTML = AdminState.users.map(u => `
    <tr>
      <td>
        <strong style="display: block;">${u.name}</strong>
        <span style="font-size: 0.72rem; color: var(--text-muted);">${u.id}</span>
      </td>
      <td>${u.email}</td>
      <td>
        <span class="user-role-badge ${u.role === 'admin' ? 'role-admin' : 'role-operario'}">
          ${u.role === 'admin' ? 'Administrador' : 'Operario'}
        </span>
      </td>
      <td style="font-size: 0.75rem; color: var(--text-muted);">${u.created_at}</td>
    </tr>
  `).join('');
}

function setupUserCreationForm() {
  const form = document.getElementById('create-user-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('new-user-name').value;
      const email = document.getElementById('new-user-email').value;
      const password = document.getElementById('new-user-password').value;
      const role = document.getElementById('new-user-role').value;

      try {
        const res = await fetch('/api/admin/users', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${AdminState.token}`
          },
          body: JSON.stringify({ name, email, password, role })
        });
        const result = await res.json();
        if (result.success) {
          showToast(`Cuenta para ${name} creada exitosamente`);
          form.reset();
          fetchTeam();
        } else {
          showToast(result.error || 'Error creando usuario');
        }
      } catch (err) {
        showToast('Error de conexión');
      }
    });
  }
}

// Listeners de búsqueda y filtrado
function setupFilterListeners() {
  const statusFilter = document.getElementById('admin-status-filter');
  if (statusFilter) statusFilter.addEventListener('change', (e) => { AdminState.filterStatus = e.target.value; fetchOrders(); });

  const shippingFilter = document.getElementById('admin-shipping-filter');
  if (shippingFilter) shippingFilter.addEventListener('change', (e) => { AdminState.filterShipping = e.target.value; fetchOrders(); });

  const methodFilter = document.getElementById('admin-method-filter');
  if (methodFilter) methodFilter.addEventListener('change', (e) => { AdminState.filterMethod = e.target.value; fetchOrders(); });

  const searchInput = document.getElementById('admin-search');
  if (searchInput) {
    let timeout = null;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => { AdminState.searchQuery = e.target.value; fetchOrders(); }, 300);
    });
  }

  const overlay = document.getElementById('admin-modal-overlay');
  if (overlay) overlay.addEventListener('click', (e) => { if (e.target === overlay) closeAdminModal(); });
}

function showToast(message) {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<span>${window.ICONS.check}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Exponer al scope global
window.fillLogin = fillLogin;
window.logout = logout;
window.switchModule = switchModule;
window.quickApproveTransfer = quickApproveTransfer;
window.openDispatchModal = openDispatchModal;
window.markAsDelivered = markAsDelivered;
window.openOrderDetailModal = openOrderDetailModal;
window.closeAdminModal = closeAdminModal;
window.saveProductPrice = saveProductPrice;
window.toggleProductStock = toggleProductStock;
window.openCreateProductModal = openCreateProductModal;
window.handleCreateProductSubmit = handleCreateProductSubmit;
