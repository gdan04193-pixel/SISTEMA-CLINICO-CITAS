// ============================================================
// static/js/pwa.js — Módulo PWA: Notificaciones Push + APIs Nativas
// Práctica 2.1: Push Notifications + Device Features
// ============================================================

// ── Clave pública VAPID (se obtiene del servidor) ────────────────────────────
// Esta clave es pública, segura para incluir en el cliente
const VAPID_PUBLIC_KEY_URL = '/api/push/vapid-public-key';

// ── Estado global del módulo ──────────────────────────────────────────────────
const PWAModule = {
  swRegistration: null,
  pushSubscription: null,
  notifPermission: Notification.permission,
  geoPermission: null,
  cameraPermission: null,
};

// ── Utilidad: Convertir clave VAPID de Base64 a Uint8Array ───────────────────
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  return new Uint8Array([...rawData].map(c => c.charCodeAt(0)));
}

// ── 1. Registrar Service Worker ───────────────────────────────────────────────
async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    console.warn('[PWA] Service Worker no soportado en este navegador.');
    updateStatus('sw-status', 'No soportado', 'error');
    return null;
  }

  try {
    const reg = await navigator.serviceWorker.register('/sw.js', {
      scope: '/'
    });
    PWAModule.swRegistration = reg;
    console.log('[PWA] Service Worker registrado:', reg.scope);
    updateStatus('sw-status', '✅ Registrado y activo', 'success');
    return reg;
  } catch (err) {
    console.error('[PWA] Error registrando SW:', err);
    updateStatus('sw-status', '❌ Error: ' + err.message, 'error');
    return null;
  }
}

// ── 2. Solicitar permiso de notificaciones ────────────────────────────────────
async function requestNotificationPermission() {
  if (!('Notification' in window)) {
    showToast('❌ Tu navegador no soporta notificaciones.', 'error');
    updateStatus('notif-status', 'No soportado', 'error');
    return 'denied';
  }

  let permission = Notification.permission;

  if (permission === 'default') {
    permission = await Notification.requestPermission();
  }

  PWAModule.notifPermission = permission;
  updatePermissionBadge('notif-badge', permission);

  if (permission === 'granted') {
    showToast('🔔 ¡Permisos de notificación concedidos!', 'success');
    updateStatus('notif-status', '✅ Permiso concedido', 'success');
    await subscribeToPush();
  } else if (permission === 'denied') {
    showToast('🔕 Notificaciones bloqueadas por el usuario.', 'warning');
    updateStatus('notif-status', '🚫 Permiso denegado', 'error');
    logPermissionEvent('notifications', 'denied');
  } else {
    updateStatus('notif-status', '⏳ Sin respuesta', 'warning');
  }

  return permission;
}

// ── 3. Suscripción Push real con VAPID ───────────────────────────────────────
async function subscribeToPush() {
  if (!PWAModule.swRegistration) {
    console.warn('[PWA] SW no registrado, no se puede suscribir al push.');
    return;
  }

  try {
    // Obtener clave pública del servidor
    const keyResponse = await fetch(VAPID_PUBLIC_KEY_URL);
    const { publicKey } = await keyResponse.json();

    const subscription = await PWAModule.swRegistration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey)
    });

    PWAModule.pushSubscription = subscription;

    // Enviar suscripción al servidor
    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()
      },
      body: JSON.stringify(subscription.toJSON())
    });

    console.log('[PWA] Suscripción push enviada al servidor:', subscription.endpoint);
    updateStatus('push-status', '✅ Suscrito correctamente', 'success');
    logPermissionEvent('push_subscription', 'granted');

  } catch (err) {
    console.error('[PWA] Error suscribiendo al push:', err);
    updateStatus('push-status', '❌ Error en suscripción', 'error');
  }
}

// ── 4. Enviar notificación de prueba ─────────────────────────────────────────
async function sendTestNotification() {
  if (PWAModule.notifPermission !== 'granted') {
    showToast('🔕 Primero concede permisos de notificación.', 'warning');
    return;
  }

  // Notificación local inmediata (sin servidor)
  if (PWAModule.swRegistration) {
    await PWAModule.swRegistration.showNotification('🏥 HealthVault – Notificación de Prueba', {
      body: 'Este es un mensaje del Sistema Médico HealthVault. ¡Las notificaciones push funcionan correctamente!',
      icon: '/static/logo.png',
      badge: '/static/logo.png',
      vibrate: [200, 100, 200],
      tag: 'test-push',
      data: { url: '/dashboard' },
      actions: [
        { action: 'open', title: '📂 Ir al Dashboard' },
        { action: 'dismiss', title: '✕ Cerrar' }
      ]
    });
    showToast('🔔 Notificación enviada correctamente.', 'success');
    logPermissionEvent('test_notification', 'sent');
  } else {
    // Fallback: Notification API directa
    new Notification('🏥 HealthVault – Prueba', {
      body: 'Notificación de prueba del sistema médico.',
      icon: '/static/logo.png'
    });
  }

  // También solicitar al servidor que envíe un push real
  try {
    await fetch('/api/push/send-test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()
      }
    });
  } catch (e) {
    console.log('[PWA] Nota: envío server-side no disponible.');
  }
}

// ── 5. Geolocalización ────────────────────────────────────────────────────────
async function requestGeolocation() {
  if (!('geolocation' in navigator)) {
    showToast('❌ Geolocalización no soportada.', 'error');
    updateStatus('geo-status', 'No soportado', 'error');
    return;
  }

  updateStatus('geo-status', '⏳ Solicitando permiso...', 'loading');
  showToast('📍 Solicitando acceso a ubicación...', 'info');

  navigator.geolocation.getCurrentPosition(
    // Éxito: permiso concedido
    (position) => {
      const { latitude, longitude, accuracy, altitude } = position.coords;
      const timestamp = new Date(position.timestamp).toLocaleString('es-MX');

      PWAModule.geoPermission = 'granted';
      updatePermissionBadge('geo-badge', 'granted');
      updateStatus('geo-status', '✅ Ubicación obtenida', 'success');
      logPermissionEvent('geolocation', 'granted');

      // Mostrar datos en el panel
      document.getElementById('geo-data').innerHTML = `
        <div class="geo-result">
          <div class="geo-row"><span class="geo-label">📍 Latitud</span><span class="geo-value">${latitude.toFixed(6)}°</span></div>
          <div class="geo-row"><span class="geo-label">📍 Longitud</span><span class="geo-value">${longitude.toFixed(6)}°</span></div>
          <div class="geo-row"><span class="geo-label">🎯 Precisión</span><span class="geo-value">±${accuracy.toFixed(0)} m</span></div>
          ${altitude !== null ? `<div class="geo-row"><span class="geo-label">⛰️ Altitud</span><span class="geo-value">${altitude.toFixed(0)} m</span></div>` : ''}
          <div class="geo-row"><span class="geo-label">🕐 Timestamp</span><span class="geo-value">${timestamp}</span></div>
        </div>
        <a href="https://maps.google.com/?q=${latitude},${longitude}" target="_blank" class="btn-map">
          🗺️ Ver en Google Maps
        </a>
      `;

      showToast(`✅ Ubicación: ${latitude.toFixed(4)}, ${longitude.toFixed(4)}`, 'success');
    },
    // Error: permiso denegado u otro error
    (error) => {
      let msg = '';
      switch (error.code) {
        case error.PERMISSION_DENIED:
          msg = '🚫 Permiso de ubicación denegado por el usuario.';
          PWAModule.geoPermission = 'denied';
          updatePermissionBadge('geo-badge', 'denied');
          logPermissionEvent('geolocation', 'denied');
          break;
        case error.POSITION_UNAVAILABLE:
          msg = '📡 Información de ubicación no disponible.';
          break;
        case error.TIMEOUT:
          msg = '⏰ Se agotó el tiempo para obtener la ubicación.';
          break;
        default:
          msg = '❌ Error desconocido al obtener la ubicación.';
      }
      updateStatus('geo-status', msg, 'error');
      showToast(msg, 'error');
      document.getElementById('geo-data').innerHTML = `<p class="perm-denied">${msg}</p>`;
    },
    // Opciones
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
  );
}

// ── 6. Cámara / Micrófono ─────────────────────────────────────────────────────
async function requestCamera(type = 'both') {
  if (!('mediaDevices' in navigator && navigator.mediaDevices.getUserMedia)) {
    showToast('❌ API de cámara no soportada.', 'error');
    updateStatus('cam-status', 'No soportado', 'error');
    return;
  }

  const constraints = {
    video: type !== 'audio' ? { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } } : false,
    audio: type !== 'video'
  };

  updateStatus('cam-status', '⏳ Solicitando permiso...', 'loading');
  showToast('📷 Solicitando acceso a cámara/micrófono...', 'info');

  try {
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    PWAModule.cameraPermission = 'granted';
    updatePermissionBadge('cam-badge', 'granted');
    updateStatus('cam-status', '✅ Cámara activa', 'success');
    logPermissionEvent('camera_microphone', 'granted');
    showToast('✅ Cámara y micrófono activados.', 'success');

    // Mostrar preview de video si está disponible
    const video = document.getElementById('camera-preview');
    if (video && stream.getVideoTracks().length > 0) {
      video.srcObject = stream;
      video.style.display = 'block';
      video.play();
      document.getElementById('cam-controls').style.display = 'flex';
    }

    // Guardar stream para poder detenerlo
    PWAModule.activeStream = stream;

    // Mostrar info de pistas de medios
    const tracks = stream.getTracks();
    document.getElementById('cam-data').innerHTML = `
      <div class="cam-info">
        ${tracks.map(t => `
          <div class="geo-row">
            <span class="geo-label">${t.kind === 'video' ? '📹' : '🎙️'} ${t.kind}</span>
            <span class="geo-value">${t.label || 'Dispositivo activo'}</span>
          </div>
        `).join('')}
      </div>
    `;

  } catch (err) {
    let msg = '';
    PWAModule.cameraPermission = 'denied';
    updatePermissionBadge('cam-badge', 'denied');
    logPermissionEvent('camera_microphone', 'denied');

    if (err.name === 'NotAllowedError') {
      msg = '🚫 Permiso de cámara denegado por el usuario.';
    } else if (err.name === 'NotFoundError') {
      msg = '📷 No se encontró dispositivo de cámara/micrófono.';
    } else if (err.name === 'NotReadableError') {
      msg = '🔒 El dispositivo está siendo usado por otra aplicación.';
    } else {
      msg = `❌ Error: ${err.message}`;
    }

    updateStatus('cam-status', msg, 'error');
    showToast(msg, 'error');
    document.getElementById('cam-data').innerHTML = `<p class="perm-denied">${msg}</p>`;
  }
}

// ── 7. Detener cámara ─────────────────────────────────────────────────────────
function stopCamera() {
  if (PWAModule.activeStream) {
    PWAModule.activeStream.getTracks().forEach(t => t.stop());
    PWAModule.activeStream = null;
    const video = document.getElementById('camera-preview');
    if (video) {
      video.srcObject = null;
      video.style.display = 'none';
    }
    document.getElementById('cam-controls').style.display = 'none';
    document.getElementById('cam-data').innerHTML = '';
    updateStatus('cam-status', '⏹️ Cámara detenida', 'warning');
    showToast('📷 Cámara detenida.', 'info');
    updatePermissionBadge('cam-badge', 'default');
  }
}

// ── 8. Capturar foto ──────────────────────────────────────────────────────────
function capturePhoto() {
  const video = document.getElementById('camera-preview');
  const canvas = document.getElementById('photo-canvas');
  if (!video || !canvas) return;

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  canvas.style.display = 'block';
  showToast('📸 Foto capturada correctamente.', 'success');
}

// ── 9. Verificar estado de permisos con Permissions API ──────────────────────
async function checkAllPermissions() {
  const permissions = ['notifications', 'geolocation', 'camera', 'microphone'];
  
  for (const perm of permissions) {
    try {
      const status = await navigator.permissions.query({ name: perm });
      console.log(`[PWA] Permiso '${perm}': ${status.state}`);
      
      status.onchange = () => {
        console.log(`[PWA] Permiso '${perm}' cambió a: ${status.state}`);
        logPermissionEvent(perm, status.state);
      };
    } catch (e) {
      console.log(`[PWA] No se puede verificar permiso '${perm}':`, e.message);
    }
  }
}

// ── Helpers de UI ─────────────────────────────────────────────────────────────
function updateStatus(elementId, message, type) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = message;
  el.className = `status-badge status-${type}`;
}

function updatePermissionBadge(elementId, state) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const icons = { granted: '✅ Concedido', denied: '🚫 Denegado', default: '❓ Pendiente', prompt: '❓ Pendiente' };
  const classes = { granted: 'perm-granted', denied: 'perm-denied-badge', default: 'perm-pending', prompt: 'perm-pending' };
  el.textContent = icons[state] || '❓ Pendiente';
  el.className = `perm-badge ${classes[state] || 'perm-pending'}`;
}

function showToast(message, type = 'info') {
  const toast = document.getElementById('pwa-toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `pwa-toast show toast-${type}`;
  clearTimeout(PWAModule.toastTimer);
  PWAModule.toastTimer = setTimeout(() => {
    toast.className = 'pwa-toast';
  }, 4000);
}

function logPermissionEvent(feature, state) {
  const log = document.getElementById('permission-log');
  if (!log) return;
  const time = new Date().toLocaleTimeString('es-MX');
  const icons = { granted: '✅', denied: '🚫', sent: '📤', prompt: '❓' };
  const entry = document.createElement('div');
  entry.className = `log-entry log-${state}`;
  entry.innerHTML = `<span class="log-time">[${time}]</span> ${icons[state] || 'ℹ️'} <strong>${feature}</strong>: ${state}`;
  log.prepend(entry);
}

function getCSRFToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : '';
}

// ── Inicialización ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  console.log('[PWA] Inicializando módulo PWA...');

  // Registrar Service Worker
  await registerServiceWorker();

  // Verificar permisos actuales
  await checkAllPermissions();

  // Mostrar estado inicial de notificaciones
  const currentPerm = Notification.permission;
  updatePermissionBadge('notif-badge', currentPerm === 'default' ? 'prompt' : currentPerm);
  updateStatus('notif-status', 
    currentPerm === 'granted' ? '✅ Permisos ya concedidos' :
    currentPerm === 'denied' ? '🚫 Permisos bloqueados en el navegador' :
    '❓ Sin permiso aún', 
    currentPerm === 'granted' ? 'success' : currentPerm === 'denied' ? 'error' : 'warning'
  );

  // Si ya tenía permiso, suscribir
  if (currentPerm === 'granted' && PWAModule.swRegistration) {
    await subscribeToPush();
  }

  // Vincular botones
  const btnNotif = document.getElementById('btn-request-notif');
  if (btnNotif) btnNotif.addEventListener('click', requestNotificationPermission);

  const btnTestNotif = document.getElementById('btn-test-notif');
  if (btnTestNotif) btnTestNotif.addEventListener('click', sendTestNotification);

  const btnGeo = document.getElementById('btn-request-geo');
  if (btnGeo) btnGeo.addEventListener('click', requestGeolocation);

  const btnCam = document.getElementById('btn-request-cam');
  if (btnCam) btnCam.addEventListener('click', () => requestCamera('both'));

  const btnCamOnly = document.getElementById('btn-request-cam-only');
  if (btnCamOnly) btnCamOnly.addEventListener('click', () => requestCamera('video'));

  const btnMicOnly = document.getElementById('btn-request-mic-only');
  if (btnMicOnly) btnMicOnly.addEventListener('click', () => requestCamera('audio'));

  const btnStopCam = document.getElementById('btn-stop-cam');
  if (btnStopCam) btnStopCam.addEventListener('click', stopCamera);

  const btnCapture = document.getElementById('btn-capture');
  if (btnCapture) btnCapture.addEventListener('click', capturePhoto);

  // ── Práctica 2.2: Controles de Instalabilidad y Caché Offline ───────────────
  const btnInstall = document.getElementById('btn-trigger-install');
  if (btnInstall) {
    btnInstall.addEventListener('click', async () => {
      if (window.pwaInstallPrompt) {
        window.pwaInstallPrompt.prompt();
        const choice = await window.pwaInstallPrompt.userChoice;
        showToast(`📲 Instalación: ${choice.outcome}`, 'info');
        logPermissionEvent('PWA Install', choice.outcome);
        window.pwaInstallPrompt = null;
      } else {
        // Si no está el prompt activo, verificar si ya está instalada o dar instrucciones
        const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
        if (isStandalone) {
          showToast('✅ ¡HealthVault ya está corriendo como PWA instalada!', 'success');
        } else {
          showToast('ℹ️ Puedes instalarla desde el ícono ➕ en la barra de direcciones de tu navegador.', 'info');
        }
        logPermissionEvent('PWA Install Check', isStandalone ? 'already_installed' : 'manual_prompt_needed');
      }
    });
  }

  const btnInspectCache = document.getElementById('btn-inspect-cache');
  if (btnInspectCache) {
    btnInspectCache.addEventListener('click', async () => {
      const resultEl = document.getElementById('cache-audit-result');
      if (!('caches' in window)) {
        if (resultEl) resultEl.innerHTML = '❌ CacheStorage no soportado en este navegador.';
        return;
      }

      try {
        const cacheNames = await caches.keys();
        let totalItems = 0;
        let detailsHtml = `<div style="margin-top:0.5rem; padding:0.5rem; background:rgba(0,0,0,0.25); border-radius:6px;">`;
        detailsHtml += `<strong>Cachés activas:</strong> ${cacheNames.join(', ')}<br>`;

        for (const name of cacheNames) {
          const cache = await caches.open(name);
          const keys = await cache.keys();
          totalItems += keys.length;
          detailsHtml += `<span style="color:#0ea5e9;">• ${name}:</span> ${keys.length} recursos cacheados<br>`;
        }
        detailsHtml += `<strong>Total de recursos en caché:</strong> ${totalItems} elementos.</div>`;

        if (resultEl) resultEl.innerHTML = detailsHtml;
        showToast(`📦 Caché auditada: ${totalItems} recursos precacheados`, 'success');
        logPermissionEvent('Cache Audit', `${totalItems} items`);
      } catch (err) {
        if (resultEl) resultEl.innerHTML = `❌ Error: ${err.message}`;
      }
    });
  }

  // Detección de display-mode
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
  const displayBadge = document.getElementById('display-mode-badge');
  if (displayBadge) {
    displayBadge.textContent = isStandalone ? '🖥️ PWA Instalada (Standalone)' : '🌐 Modo Navegador (Tab)';
  }

  // Detección de contexto seguro
  const secureBadge = document.getElementById('secure-context-badge');
  if (secureBadge) {
    secureBadge.textContent = window.isSecureContext ? '🔒 Contexto Seguro W3C (HTTPS/Localhost)' : '⚠️ Inseguro';
    secureBadge.className = window.isSecureContext ? 'status-badge status-success' : 'status-badge status-error';
  }

  // Detección de conexión
  const netBadge = document.getElementById('network-status-badge');
  function updateNetBadge() {
    if (!netBadge) return;
    if (navigator.onLine) {
      netBadge.textContent = '🟢 En Línea (Online)';
      netBadge.className = 'perm-badge perm-granted';
    } else {
      netBadge.textContent = '🔴 Desconectado (Offline)';
      netBadge.className = 'perm-badge perm-denied';
    }
  }
  window.addEventListener('online', updateNetBadge);
  window.addEventListener('offline', updateNetBadge);
  updateNetBadge();

  logPermissionEvent('PWA Module', 'iniciado (v2.2)');
  console.log('[PWA] Módulo iniciado correctamente (Práctica 2.2).');
});

