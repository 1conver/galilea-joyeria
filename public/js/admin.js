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
  const avatarEl = document.getElementById('header-user-avatar');

  if (nameEl) nameEl.textContent = user.name;
  if (avatarEl && user.name) avatarEl.textContent = user.name.charAt(0).toUpperCase();
  if (roleBadge) {
    roleBadge.textContent = user.role === 'admin' ? 'Admin' : 'Operario';
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
// MÓDULO 2: CATÁLOGO & FOTOGRAFÍAS (SOLO ADMIN)
// =========================================================================

// --- UTILIDAD DE SUBIDA DE IMÁGENES EN LOCAL ---
async function uploadImageFile(file) {
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/admin/upload', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${AdminState.token}`
      },
      body: formData
    });
    const data = await res.json();
    if (data.success && data.url) return data.url;
    throw new Error(data.error || 'Error al subir archivo');
  } catch (err) {
    // Respaldo Base64 JSON
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const res = await fetch('/api/admin/upload', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${AdminState.token}`
            },
            body: JSON.stringify({ filename: file.name, data: reader.result })
          });
          const data = await res.json();
          if (data.success && data.url) resolve(data.url);
          else reject(new Error(data.error || 'Error al subir imagen'));
        } catch (e) {
          reject(e);
        }
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }
}

// Vinculación de zona Drag & Drop + Input File + Previsualización en Vivo
function bindUploadZone(zoneId, fileInputId, urlInputId, previewImgId, statusId) {
  const zone = document.getElementById(zoneId);
  const fileInput = document.getElementById(fileInputId);
  const urlInput = document.getElementById(urlInputId);
  const previewImg = document.getElementById(previewImgId);
  const statusEl = document.getElementById(statusId);

  if (!zone || !fileInput) return;

  zone.addEventListener('click', (e) => {
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'BUTTON') {
      fileInput.click();
    }
  });

  ['dragenter', 'dragover'].forEach(eventName => {
    zone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.add('dragover');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    zone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove('dragover');
    }, false);
  });

  zone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      processSelectedFile(dt.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      processSelectedFile(e.target.files[0]);
    }
  });

  if (urlInput) {
    urlInput.addEventListener('input', (e) => {
      const val = e.target.value.trim();
      if (val && previewImg) {
        previewImg.src = val;
        previewImg.style.display = 'block';
        if (statusEl) statusEl.innerHTML = `<span style="color: #205C33; font-weight: 600;">✓ Imagen vinculada por URL</span>`;
      }
    });
  }

  async function processSelectedFile(file) {
    if (!file.type.startsWith('image/')) {
      showToast('Por favor seleccioná una imagen válida (JPG, PNG, WebP)');
      return;
    }

    // Previsualización instantánea local
    const tempUrl = URL.createObjectURL(file);
    if (previewImg) {
      previewImg.src = tempUrl;
      previewImg.style.display = 'block';
    }
    if (statusEl) {
      statusEl.innerHTML = `<span style="color: var(--admin-rose-primary); font-weight: 600;">⏳ Guardando archivo en servidor local...</span>`;
    }

    try {
      const localUrl = await uploadImageFile(file);
      if (urlInput) urlInput.value = localUrl;
      if (previewImg) previewImg.src = localUrl;
      if (statusEl) {
        statusEl.innerHTML = `<span style="color: #205C33; font-weight: 700;">✓ Archivo local guardado: ${file.name}</span>`;
      }
      showToast(`Foto '${file.name}' guardada en local`);
    } catch (err) {
      if (statusEl) {
        statusEl.innerHTML = `<span style="color: #962332; font-weight: 600;">✕ Error al guardar: ${err.message}</span>`;
      }
      showToast('Error al procesar la foto');
    }
  }
}

// Alternar entre pestaña "Subir Archivo Local" y "Link URL"
function toggleUploadTab(targetPrefix, mode) {
  const localTabBtn = document.getElementById(`${targetPrefix}-tab-local`);
  const urlTabBtn = document.getElementById(`${targetPrefix}-tab-url`);
  const localPane = document.getElementById(`${targetPrefix}-pane-local`);
  const urlPane = document.getElementById(`${targetPrefix}-pane-url`);

  if (mode === 'local') {
    if (localTabBtn) localTabBtn.classList.add('active');
    if (urlTabBtn) urlTabBtn.classList.remove('active');
    if (localPane) localPane.style.display = 'block';
    if (urlPane) urlPane.style.display = 'none';
  } else {
    if (localTabBtn) localTabBtn.classList.remove('active');
    if (urlTabBtn) urlTabBtn.classList.add('active');
    if (localPane) localPane.style.display = 'none';
    if (urlPane) urlPane.style.display = 'block';
  }
}

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
  const counterEl = document.getElementById('catalog-total-counter');
  if (!tbody) return;

  let prods = AdminState.products || [];

  // Filtro de búsqueda
  if (AdminState.catalogQuery) {
    const q = AdminState.catalogQuery;
    prods = prods.filter(p =>
      (p.name && p.name.toLowerCase().includes(q)) ||
      (p.id && p.id.toLowerCase().includes(q)) ||
      (p.metal && p.metal.toLowerCase().includes(q)) ||
      (p.category_label && p.category_label.toLowerCase().includes(q)) ||
      (p.badge && p.badge.toLowerCase().includes(q))
    );
  }

  // Filtro de categoría
  if (AdminState.catalogCategory && AdminState.catalogCategory !== 'todos') {
    if (AdminState.catalogCategory === 'diamantes') {
      prods = prods.filter(p => p.category === 'diamantes' || (p.badge && p.badge.toLowerCase().includes('alta')) || p.price >= 400000);
    } else if (AdminState.catalogCategory === 'limitada') {
      prods = prods.filter(p => p.category === 'limitada' || (p.badge && p.badge.toLowerCase().includes('limitada')));
    } else {
      prods = prods.filter(p => p.category === AdminState.catalogCategory);
    }
  }

  // Filtro de disponibilidad
  if (AdminState.catalogStock === 'in_stock') {
    prods = prods.filter(p => p.in_stock);
  } else if (AdminState.catalogStock === 'out_of_stock') {
    prods = prods.filter(p => !p.in_stock);
  }

  if (counterEl) {
    counterEl.textContent = `${prods.length} ${prods.length === 1 ? 'joya' : 'joyas'} en catálogo`;
  }

  if (prods.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; padding: 3rem 1rem; color: var(--admin-text-muted);">
          No se encontraron piezas en el catálogo con los filtros actuales.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = prods.map(prod => `
    <tr>
      <td>
        <div style="display: flex; align-items: center; gap: 1rem;">
          <div style="position: relative; cursor: pointer;" onclick="openEditProductModal('${prod.id}')" title="Hacé clic para cambiar fotos o editar">
            <img src="${prod.primary_image}" alt="${prod.name}" class="product-thumb-preview">
            ${prod.secondary_image ? `<span style="position: absolute; bottom: -3px; right: -3px; background: #3A1822; color: #FFF; font-size: 0.6rem; padding: 0.1rem 0.35rem; border-radius: 9999px; font-weight: 700;">+1</span>` : ''}
          </div>
          <div>
            <strong style="display: block; font-size: 0.95rem; color: var(--admin-text-main); cursor: pointer;" onclick="openEditProductModal('${prod.id}')">
              ${prod.name}
            </strong>
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.2rem;">
              <span style="font-size: 0.72rem; color: var(--admin-rose-deep); font-weight: 600;">${prod.badge || ''}</span>
              <span style="font-size: 0.68rem; color: var(--admin-text-muted); font-family: monospace;">ID: ${prod.id}</span>
            </div>
          </div>
        </div>
      </td>
      <td>
        <div style="font-weight: 600;">${prod.category_label || prod.category}</div>
        <div style="font-size: 0.72rem; color: var(--admin-text-muted); margin-top: 0.15rem;">${prod.metal}</div>
      </td>
      <td>
        <div style="display: flex; align-items: center; gap: 0.4rem;">
          <input type="number" id="price-input-${prod.id}" value="${prod.price}" class="form-input" style="width: 125px; padding: 0.35rem 0.5rem; font-size: 0.85rem; font-weight: 600;">
          <button class="btn-op-action" onclick="saveProductPrice('${prod.id}')" title="Guardar Precio">Guardar</button>
        </div>
      </td>
      <td>
        <button class="badge-status ${prod.in_stock ? 'badge-approved' : 'badge-rejected'}" style="cursor: pointer; border: none;" onclick="toggleProductStock('${prod.id}', ${!prod.in_stock})">
          <span>${prod.in_stock ? '● En Stock' : '✕ Agotado'}</span>
        </button>
      </td>
      <td style="text-align: right;">
        <div class="table-action-btns" style="justify-content: flex-end;">
          <button class="btn-op-action btn-op-photo" onclick="openEditProductModal('${prod.id}')" title="Cambiar Fotos y Datos">
            ${window.ICONS.image || ''}
            <span>Cambiar Fotos</span>
          </button>
          <button class="btn-op-action" onclick="openEditProductModal('${prod.id}')" title="Editar Detalles">
            ${window.ICONS.edit || ''}
            <span>Editar</span>
          </button>
          <button class="btn-op-action btn-op-danger" onclick="deleteProduct('${prod.id}', '${(prod.name || '').replace(/'/g, "\\'")}')" title="Eliminar del Catálogo">
            ${window.ICONS.trash || ''}
          </button>
        </div>
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

// --- MODAL DE DAR DE ALTA JOYA (SUBIDA LOCAL O LINK) ---
function openCreateProductModal() {
  const overlay = document.getElementById('admin-modal-overlay');
  const container = document.getElementById('admin-modal-content');

  const defaultImg = "https://images.unsplash.com/photo-1605100804763-247f67b3557e?auto=format&fit=crop&w=900&q=85";
  const defaultSecImg = "https://images.unsplash.com/photo-1603561591411-07134e71a2a9?auto=format&fit=crop&w=900&q=85";

  container.innerHTML = `
    <div class="admin-modal-card" style="max-width: 680px;">
      <button class="btn-close-modal" onclick="closeAdminModal()">${window.ICONS.close}</button>
      <h2 class="admin-modal-title">Dar de Alta Nueva Joya</h2>
      <p class="admin-modal-subtitle">Podés subir las fotos directamente desde tu computadora o pegar un enlace web.</p>

      <form id="create-product-form" onsubmit="handleCreateProductSubmit(event)">
        
        <div class="form-group" style="margin-bottom: 1.2rem;">
          <label class="form-label">Nombre de la Pieza</label>
          <input type="text" id="new-prod-name" class="form-input" placeholder="Ej. Gargantilla Solitario Brilliante" required>
        </div>

        <div class="form-row" style="margin-bottom: 1.2rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
          <div class="form-group">
            <label class="form-label">Categoría</label>
            <select id="new-prod-category" class="form-select">
              <option value="anillos">Anillos</option>
              <option value="collares">Collares</option>
              <option value="aros">Aros</option>
              <option value="pulseras">Pulseras</option>
              <option value="diamantes">Alta Joyería & Diamantes</option>
              <option value="limitada">Edición Limitada</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Metal Noble</label>
            <select id="new-prod-metal" class="form-select">
              <option value="Oro 18K">Oro 18K Amarillo</option>
              <option value="Oro Blanco 18K">Oro Blanco 18K</option>
              <option value="Plata 925">Plata 925</option>
              <option value="Plata 925 Bañada en Oro">Plata 925 Bañada en Oro 24K</option>
            </select>
          </div>
        </div>

        <div class="form-row" style="margin-bottom: 1.2rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
          <div class="form-group">
            <label class="form-label">Precio en ARS ($)</label>
            <input type="number" id="new-prod-price" class="form-input" placeholder="Ej. 320000" min="100" required>
          </div>
          <div class="form-group">
            <label class="form-label">Etiqueta / Badge Promocional</label>
            <input type="text" id="new-prod-badge" class="form-input" placeholder="Ej. Nuevo / Best Seller / Edición Limitada" value="Nuevo">
          </div>
        </div>

        <!-- FOTOGRAFÍA PRINCIPAL -->
        <div style="background: #FFFDFD; border: 1px solid var(--admin-rose-border); border-radius: 14px; padding: 1.2rem; margin-bottom: 1.2rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
            <label class="form-label" style="margin: 0;">Fotografía Principal (Portada de la Joya)</label>
            <div class="upload-method-tabs" style="margin: 0;">
              <button type="button" class="upload-tab-btn active" id="new-pri-tab-local" onclick="toggleUploadTab('new-pri', 'local')">📁 Subir desde mi PC</button>
              <button type="button" class="upload-tab-btn" id="new-pri-tab-url" onclick="toggleUploadTab('new-pri', 'url')">🔗 Enlace URL</button>
            </div>
          </div>

          <!-- Opción 1: Archivo local -->
          <div id="new-pri-pane-local">
            <div class="upload-zone-wrapper" id="new-pri-zone">
              <input type="file" id="new-pri-file" accept="image/*" style="display: none;">
              <div class="upload-zone-icon">
                ${window.ICONS.upload || '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>'}
              </div>
              <div class="upload-zone-title">Hacé clic para elegir una foto o arrastrala acá</div>
              <div class="upload-zone-desc">Formatos: JPG, PNG, WebP o AVIF (sin límites ajetreados)</div>
            </div>
          </div>

          <!-- Opción 2: URL externa -->
          <div id="new-pri-pane-url" style="display: none; margin-top: 0.6rem;">
            <input type="url" id="new-prod-img" class="form-input" placeholder="https://..." value="${defaultImg}">
          </div>

          <!-- Preview & Estado -->
          <div class="image-live-preview-box">
            <img src="${defaultImg}" id="new-pri-preview" class="image-live-preview-img" alt="Vista previa principal">
            <div class="image-preview-info">
              <div class="image-preview-filename">Foto de Portada</div>
              <div id="new-pri-status" class="image-preview-status">✓ Lista para incorporar</div>
            </div>
          </div>
        </div>

        <!-- FOTOGRAFÍA SECUNDARIA (OPCIONAL) -->
        <div style="background: #FFFDFD; border: 1px solid var(--admin-rose-border); border-radius: 14px; padding: 1.2rem; margin-bottom: 1.2rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
            <label class="form-label" style="margin: 0;">Fotografía Secundaria (Detalle o puesta en modelo)</label>
            <div class="upload-method-tabs" style="margin: 0;">
              <button type="button" class="upload-tab-btn active" id="new-sec-tab-local" onclick="toggleUploadTab('new-sec', 'local')">📁 Subir desde mi PC</button>
              <button type="button" class="upload-tab-btn" id="new-sec-tab-url" onclick="toggleUploadTab('new-sec', 'url')">🔗 Enlace URL</button>
            </div>
          </div>

          <div id="new-sec-pane-local">
            <div class="upload-zone-wrapper" id="new-sec-zone">
              <input type="file" id="new-sec-file" accept="image/*" style="display: none;">
              <div class="upload-zone-icon">
                ${window.ICONS.upload || '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>'}
              </div>
              <div class="upload-zone-title">Subir foto secundaria opcional</div>
              <div class="upload-zone-desc">Se mostrará al pasar el cursor o en la galería detallada</div>
            </div>
          </div>

          <div id="new-sec-pane-url" style="display: none; margin-top: 0.6rem;">
            <input type="url" id="new-prod-sec-img" class="form-input" placeholder="https://..." value="${defaultSecImg}">
          </div>

          <div class="image-live-preview-box">
            <img src="${defaultSecImg}" id="new-sec-preview" class="image-live-preview-img" alt="Vista previa secundaria">
            <div class="image-preview-info">
              <div class="image-preview-filename">Foto de Detalle / Ángulo Secundario</div>
              <div id="new-sec-status" class="image-preview-status">✓ Lista</div>
            </div>
          </div>
        </div>

        <div class="form-group" style="margin-bottom: 1.6rem;">
          <label class="form-label">Descripción Editorial & Taller</label>
          <textarea id="new-prod-desc" class="form-input" rows="3" placeholder="Detalles de manufactura artesanal, tipo de engaste, cierre o terminación..."></textarea>
        </div>

        <div style="display: flex; gap: 0.8rem; justify-content: flex-end;">
          <button type="button" class="btn-luxury-outline" onclick="closeAdminModal()">Cancelar</button>
          <button type="submit" class="btn-luxury">
            <span>Incorporar Joya al Catálogo</span>
          </button>
        </div>
      </form>
    </div>
  `;

  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';

  // Configurar zonas de subida local
  setTimeout(() => {
    bindUploadZone('new-pri-zone', 'new-pri-file', 'new-prod-img', 'new-pri-preview', 'new-pri-status');
    bindUploadZone('new-sec-zone', 'new-sec-file', 'new-prod-sec-img', 'new-sec-preview', 'new-sec-status');
  }, 50);
}

async function handleCreateProductSubmit(e) {
  e.preventDefault();
  const name = document.getElementById('new-prod-name').value.trim();
  const category = document.getElementById('new-prod-category').value;
  const metal = document.getElementById('new-prod-metal').value;
  const price = parseFloat(document.getElementById('new-prod-price').value);
  const badge = document.getElementById('new-prod-badge').value.trim();
  const primary_image = document.getElementById('new-prod-img').value.trim();
  const secondary_image = document.getElementById('new-prod-sec-img') ? document.getElementById('new-prod-sec-img').value.trim() : '';
  const description = document.getElementById('new-prod-desc').value.trim();

  if (!name || price <= 0 || !primary_image) {
    showToast('Por favor completá el nombre, precio y foto principal');
    return;
  }

  try {
    const res = await fetch('/api/admin/products', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AdminState.token}`
      },
      body: JSON.stringify({ name, category, metal, price, badge, primary_image, secondary_image, description })
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Joya '${name}' incorporada al catálogo`);
      closeAdminModal();
      fetchCatalog();
    } else {
      showToast(result.error || 'Error al incorporar pieza');
    }
  } catch (err) {
    showToast('Error de conexión');
  }
}

// --- MODAL DE EDICIÓN DE JOYA Y CAMBIO DE FOTOS (SUBIDA LOCAL O LINK) ---
function openEditProductModal(productId) {
  const prod = (AdminState.products || []).find(p => p.id === productId);
  if (!prod) return;

  const overlay = document.getElementById('admin-modal-overlay');
  const container = document.getElementById('admin-modal-content');

  const currentPriImg = prod.primary_image || "https://images.unsplash.com/photo-1605100804763-247f67b3557e?auto=format&fit=crop&w=900&q=85";
  const currentSecImg = prod.secondary_image || "";

  container.innerHTML = `
    <div class="admin-modal-card" style="max-width: 700px;">
      <button class="btn-close-modal" onclick="closeAdminModal()">${window.ICONS.close}</button>
      
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.2rem;">
        <div>
          <span style="font-size: 0.7rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--admin-rose-deep); font-weight: 700;">
            Editor de Pieza & Fotos
          </span>
          <h2 class="admin-modal-title" style="margin-top: 0.2rem;">${prod.name}</h2>
          <div style="font-size: 0.75rem; color: var(--admin-text-muted); font-family: monospace;">Código: ${prod.id}</div>
        </div>
        <span class="badge-status ${prod.in_stock ? 'badge-approved' : 'badge-rejected'}">
          ${prod.in_stock ? 'En Stock' : 'Agotado'}
        </span>
      </div>

      <form id="edit-product-form" onsubmit="handleEditProductSubmit(event, '${prod.id}')">
        
        <!-- FOTOGRAFÍA PRINCIPAL ACTUAL + REEMPLAZO -->
        <div style="background: #FFFDFD; border: 1.5px solid var(--admin-rose-border); border-radius: 14px; padding: 1.2rem; margin-bottom: 1.2rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
            <strong style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--admin-text-main);">
              Fotografía Principal (Portada)
            </strong>
            <div class="upload-method-tabs" style="margin: 0;">
              <button type="button" class="upload-tab-btn active" id="edit-pri-tab-local" onclick="toggleUploadTab('edit-pri', 'local')">📁 Subir desde mi PC</button>
              <button type="button" class="upload-tab-btn" id="edit-pri-tab-url" onclick="toggleUploadTab('edit-pri', 'url')">🔗 Enlace URL</button>
            </div>
          </div>

          <div id="edit-pri-pane-local">
            <div class="upload-zone-wrapper" id="edit-pri-zone">
              <input type="file" id="edit-pri-file" accept="image/*" style="display: none;">
              <div class="upload-zone-icon">
                ${window.ICONS.upload || '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>'}
              </div>
              <div class="upload-zone-title">Hacé clic para cambiar por un archivo de tu PC</div>
              <div class="upload-zone-desc">O arrastrá una nueva foto directamente acá</div>
            </div>
          </div>

          <div id="edit-pri-pane-url" style="display: none; margin-top: 0.6rem;">
            <input type="url" id="edit-prod-img" class="form-input" placeholder="https://..." value="${currentPriImg}">
          </div>

          <div class="image-live-preview-box">
            <img src="${currentPriImg}" id="edit-pri-preview" class="image-live-preview-img" alt="Foto principal">
            <div class="image-preview-info">
              <div class="image-preview-filename">Foto Principal Activa</div>
              <div id="edit-pri-status" class="image-preview-status">✓ En uso en el catálogo</div>
            </div>
          </div>
        </div>

        <!-- FOTOGRAFÍA SECUNDARIA ACTUAL + REEMPLAZO -->
        <div style="background: #FFFDFD; border: 1.5px solid var(--admin-rose-border); border-radius: 14px; padding: 1.2rem; margin-bottom: 1.4rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
            <strong style="font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--admin-text-main);">
              Fotografía Secundaria (Detalle o puesta en cuerpo)
            </strong>
            <div class="upload-method-tabs" style="margin: 0;">
              <button type="button" class="upload-tab-btn active" id="edit-sec-tab-local" onclick="toggleUploadTab('edit-sec', 'local')">📁 Subir desde mi PC</button>
              <button type="button" class="upload-tab-btn" id="edit-sec-tab-url" onclick="toggleUploadTab('edit-sec', 'url')">🔗 Enlace URL</button>
            </div>
          </div>

          <div id="edit-sec-pane-local">
            <div class="upload-zone-wrapper" id="edit-sec-zone">
              <input type="file" id="edit-sec-file" accept="image/*" style="display: none;">
              <div class="upload-zone-icon">
                ${window.ICONS.upload || '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>'}
              </div>
              <div class="upload-zone-title">Subir o cambiar foto secundaria</div>
              <div class="upload-zone-desc">Ideal para mostrar detalles de engaste o vista alternativa</div>
            </div>
          </div>

          <div id="edit-sec-pane-url" style="display: none; margin-top: 0.6rem;">
            <input type="url" id="edit-prod-sec-img" class="form-input" placeholder="https://..." value="${currentSecImg}">
          </div>

          <div class="image-live-preview-box">
            <img src="${currentSecImg || 'https://images.unsplash.com/photo-1603561591411-07134e71a2a9?auto=format&fit=crop&w=900&q=85'}" id="edit-sec-preview" class="image-live-preview-img" alt="Foto secundaria">
            <div class="image-preview-info">
              <div class="image-preview-filename">Foto Secundaria</div>
              <div id="edit-sec-status" class="image-preview-status">${currentSecImg ? '✓ Activa' : 'Opcional (sin foto aún)'}</div>
            </div>
          </div>
        </div>

        <!-- DATOS EDITABLES DE LA JOYA -->
        <div class="form-group" style="margin-bottom: 1.2rem;">
          <label class="form-label">Nombre de la Joya</label>
          <input type="text" id="edit-prod-name" class="form-input" value="${prod.name || ''}" required>
        </div>

        <div class="form-row" style="margin-bottom: 1.2rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
          <div class="form-group">
            <label class="form-label">Categoría</label>
            <select id="edit-prod-category" class="form-select">
              <option value="anillos" ${prod.category === 'anillos' ? 'selected' : ''}>Anillos</option>
              <option value="collares" ${prod.category === 'collares' ? 'selected' : ''}>Collares</option>
              <option value="aros" ${prod.category === 'aros' ? 'selected' : ''}>Aros</option>
              <option value="pulseras" ${prod.category === 'pulseras' ? 'selected' : ''}>Pulseras</option>
              <option value="diamantes" ${prod.category === 'diamantes' ? 'selected' : ''}>Alta Joyería & Diamantes</option>
              <option value="limitada" ${prod.category === 'limitada' ? 'selected' : ''}>Edición Limitada</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Metal Noble</label>
            <select id="edit-prod-metal" class="form-select">
              <option value="Oro 18K" ${prod.metal === 'Oro 18K' ? 'selected' : ''}>Oro 18K Amarillo</option>
              <option value="Oro Blanco 18K" ${prod.metal === 'Oro Blanco 18K' ? 'selected' : ''}>Oro Blanco 18K</option>
              <option value="Plata 925" ${prod.metal === 'Plata 925' ? 'selected' : ''}>Plata 925</option>
              <option value="Plata 925 Bañada en Oro" ${prod.metal && prod.metal.includes('Bañada') ? 'selected' : ''}>Plata 925 Bañada en Oro 24K</option>
            </select>
          </div>
        </div>

        <div class="form-row" style="margin-bottom: 1.2rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
          <div class="form-group">
            <label class="form-label">Precio en ARS ($)</label>
            <input type="number" id="edit-prod-price" class="form-input" value="${prod.price || 0}" required>
          </div>
          <div class="form-group">
            <label class="form-label">Etiqueta / Badge</label>
            <input type="text" id="edit-prod-badge" class="form-input" value="${prod.badge || ''}" placeholder="Ej. Best Seller, Edición Limitada...">
          </div>
        </div>

        <div class="form-group" style="margin-bottom: 1.2rem;">
          <label class="form-label">Disponibilidad en Taller</label>
          <label style="display: flex; align-items: center; gap: 0.6rem; cursor: pointer; font-size: 0.85rem;">
            <input type="checkbox" id="edit-prod-stock" ${prod.in_stock ? 'checked' : ''} style="width: 18px; height: 18px; accent-color: var(--admin-rose-primary);">
            <span>Pieza disponible para compra inmediata (En Stock)</span>
          </label>
        </div>

        <div class="form-group" style="margin-bottom: 1.6rem;">
          <label class="form-label">Descripción Editorial & Orfebrería</label>
          <textarea id="edit-prod-desc" class="form-input" rows="3">${prod.description || ''}</textarea>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--admin-rose-border); padding-top: 1.2rem;">
          <button type="button" class="btn-op-action btn-op-danger" onclick="deleteProduct('${prod.id}', '${(prod.name || '').replace(/'/g, "\\'")}')">
            ${window.ICONS.trash || ''} <span>Eliminar Joya</span>
          </button>
          
          <div style="display: flex; gap: 0.8rem;">
            <button type="button" class="btn-luxury-outline" onclick="closeAdminModal()">Cancelar</button>
            <button type="submit" class="btn-luxury">
              <span>Guardar Cambios</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  `;

  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';

  // Configurar zonas de subida local
  setTimeout(() => {
    bindUploadZone('edit-pri-zone', 'edit-pri-file', 'edit-prod-img', 'edit-pri-preview', 'edit-pri-status');
    bindUploadZone('edit-sec-zone', 'edit-sec-file', 'edit-prod-sec-img', 'edit-sec-preview', 'edit-sec-status');
  }, 50);
}

async function handleEditProductSubmit(e, productId) {
  e.preventDefault();
  const name = document.getElementById('edit-prod-name').value.trim();
  const category = document.getElementById('edit-prod-category').value;
  const metal = document.getElementById('edit-prod-metal').value;
  const price = parseFloat(document.getElementById('edit-prod-price').value);
  const badge = document.getElementById('edit-prod-badge').value.trim();
  const in_stock = document.getElementById('edit-prod-stock').checked;
  const primary_image = document.getElementById('edit-prod-img').value.trim();
  const secondary_image = document.getElementById('edit-prod-sec-img') ? document.getElementById('edit-prod-sec-img').value.trim() : '';
  const description = document.getElementById('edit-prod-desc').value.trim();

  try {
    const res = await fetch(`/api/admin/products/${productId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AdminState.token}`
      },
      body: JSON.stringify({
        name,
        category,
        metal,
        price,
        badge,
        in_stock,
        primary_image,
        secondary_image,
        description
      })
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Joya '${name}' actualizada con éxito`);
      closeAdminModal();
      fetchCatalog();
    } else {
      showToast(result.error || 'Error al actualizar la joya');
    }
  } catch (err) {
    showToast('Error de conexión al guardar cambios');
  }
}

// --- ELIMINAR JOYA DEL CATÁLOGO ---
async function deleteProduct(productId, jewelName) {
  if (!confirm(`¿Estás seguro/a de que querés eliminar la joya "${jewelName}" del catálogo de GALILEA Atelier? Esta acción no se puede deshacer.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/admin/products/${productId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${AdminState.token}`
      }
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Joya "${jewelName}" eliminada del catálogo`);
      closeAdminModal();
      fetchCatalog();
    } else {
      showToast(result.error || 'Error al eliminar joya');
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

  // Filtros del Catálogo de Joyas
  const catalogSearch = document.getElementById('catalog-search');
  if (catalogSearch) {
    let catTimeout = null;
    catalogSearch.addEventListener('input', (e) => {
      clearTimeout(catTimeout);
      catTimeout = setTimeout(() => {
        AdminState.catalogQuery = e.target.value.trim().toLowerCase();
        renderCatalogTable();
      }, 200);
    });
  }

  const catalogCatFilter = document.getElementById('catalog-category-filter');
  if (catalogCatFilter) {
    catalogCatFilter.addEventListener('change', (e) => {
      AdminState.catalogCategory = e.target.value;
      renderCatalogTable();
    });
  }

  const catalogStockFilter = document.getElementById('catalog-stock-filter');
  if (catalogStockFilter) {
    catalogStockFilter.addEventListener('change', (e) => {
      AdminState.catalogStock = e.target.value;
      renderCatalogTable();
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
  toast.innerHTML = `<span>${window.ICONS.check || '✓'}</span><span>${message}</span>`;
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
window.openEditProductModal = openEditProductModal;
window.handleEditProductSubmit = handleEditProductSubmit;
window.deleteProduct = deleteProduct;
window.toggleUploadTab = toggleUploadTab;

