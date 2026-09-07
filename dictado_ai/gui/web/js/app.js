/**
 * DictadoAI - Super Whisper Web Interface Controller
 * Connects DOM to Qt WebEngine through QWebChannel
 */

(function () {
  'use strict';

  let bridge = null;
  let historyCache = [];
  let currentView = 'home';
  let availableDevices = [];

  // DOM Elements
  const sidebar = document.getElementById('sidebar');
  const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
  const navItems = document.querySelectorAll('.nav-item');
  const viewPanels = document.querySelectorAll('.view-panel');
  const micSelectorBtn = document.getElementById('micSelectorBtn');
  const micDropdownMenu = document.getElementById('micDropdownMenu');
  const activeMicName = document.getElementById('activeMicName');
  const historyListContainer = document.getElementById('historyListContainer');
  const historySearchInput = document.getElementById('historySearchInput');
  const historyCountBadge = document.getElementById('historyCountBadge');
  const btnRefreshHistory = document.getElementById('btnRefreshHistory');
  const soundVuBar = document.getElementById('soundVuBar');
  const soundDbLabel = document.getElementById('soundDbLabel');
  const soundDeviceSelect = document.getElementById('soundDeviceSelect');
  const cfgThemeDark = document.getElementById('cfgThemeDark');

  // Window Controls
  const btnMinimize = document.getElementById('btnMinimize');
  const btnMaximize = document.getElementById('btnMaximize');
  const btnClose = document.getElementById('btnClose');

  // 1. Navigation & View Switching
  function switchView(viewName) {
    currentView = viewName;
    navItems.forEach(item => {
      if (item.dataset.view === viewName) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    viewPanels.forEach(panel => {
      if (panel.id === `view-${viewName}`) {
        panel.classList.add('active');
      } else {
        panel.classList.remove('active');
      }
    });

    if (viewName === 'history') {
      fetchHistory();
    } else if (viewName === 'vocabulary') {
      fetchVocabulary();
    } else if (viewName === 'modes') {
      fetchModes();
    } else if (viewName === 'home') {
      fetchDashboardMetrics();
    }
  }

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      switchView(item.dataset.view);
    });
  });

  document.querySelectorAll('[data-goto-view]').forEach(item => {
    item.addEventListener('click', () => {
      switchView(item.dataset.gotoView);
    });
  });

  // Sidebar collapse
  sidebarToggleBtn.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
  });

  // Window control buttons
  if (btnMinimize) {
    btnMinimize.addEventListener('click', () => {
      if (bridge) bridge.minimizeWindow();
    });
  }
  if (btnMaximize) {
    btnMaximize.addEventListener('click', () => {
      if (bridge) bridge.maximizeWindow();
    });
  }
  if (btnClose) {
    btnClose.addEventListener('click', () => {
      if (bridge) bridge.closeWindow();
    });
  }

  // 2. Microphone Selector Dropdown
  micSelectorBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    micDropdownMenu.classList.toggle('show');
  });

  document.addEventListener('click', () => {
    micDropdownMenu.classList.remove('show');
  });

  function renderDevices(devices, selectedKey) {
    availableDevices = devices || [];
    micDropdownMenu.innerHTML = '';
    if (soundDeviceSelect) soundDeviceSelect.innerHTML = '';

    const defaultItem = document.createElement('div');
    defaultItem.className = `dropdown-item ${!selectedKey ? 'active' : ''}`;
    defaultItem.textContent = 'Sistema predeterminado';
    defaultItem.dataset.micKey = '';
    defaultItem.addEventListener('click', () => selectMic(null, 'Sistema predeterminado'));
    micDropdownMenu.appendChild(defaultItem);

    if (soundDeviceSelect) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'Sistema predeterminado';
      opt.selected = !selectedKey;
      soundDeviceSelect.appendChild(opt);
    }

    let foundSelected = false;
    availableDevices.forEach(dev => {
      const isSel = selectedKey === dev.key;
      if (isSel) {
        foundSelected = true;
        activeMicName.textContent = dev.label;
      }

      const item = document.createElement('div');
      item.className = `dropdown-item ${isSel ? 'active' : ''}`;
      item.textContent = dev.label;
      item.dataset.micKey = dev.key;
      item.addEventListener('click', () => selectMic(dev.key, dev.label));
      micDropdownMenu.appendChild(item);

      if (soundDeviceSelect) {
        const opt = document.createElement('option');
        opt.value = dev.key;
        opt.textContent = dev.label;
        opt.selected = isSel;
        soundDeviceSelect.appendChild(opt);
      }
    });

    if (!selectedKey || !foundSelected) {
      activeMicName.textContent = 'Sistema predeterminado';
    }
  }

  function selectMic(key, label) {
    activeMicName.textContent = label;
    if (bridge) {
      bridge.setAudioDevice(key || '', label);
    }
    micDropdownMenu.classList.remove('show');
  }

  if (soundDeviceSelect) {
    soundDeviceSelect.addEventListener('change', (e) => {
      const key = e.target.value;
      const label = e.target.options[e.target.selectedIndex].text;
      selectMic(key || null, label);
    });
  }

  // 3. History Management
  function formatRelativeTime(isoTimestamp) {
    if (!isoTimestamp) return '';
    try {
      const d = new Date(isoTimestamp);
      const now = new Date();
      const diffSec = Math.floor((now - d) / 1000);

      if (diffSec < 60) return 'Hace unos segundos';
      if (diffSec < 3600) return `Hace ${Math.floor(diffSec / 60)} min`;
      if (diffSec < 86400) return `Hoy ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoTimestamp;
    }
  }

  function renderHistory(items) {
    historyCache = items || [];
    const query = (historySearchInput.value || '').trim().toLowerCase();

    const filtered = historyCache.filter(item => {
      if (!query) return true;
      return (item.text || '').toLowerCase().includes(query) ||
             (item.raw_asr || '').toLowerCase().includes(query);
    });

    historyCountBadge.textContent = `${filtered.length} transcripción${filtered.length === 1 ? '' : 'es'}`;
    historyListContainer.innerHTML = '';

    if (filtered.length === 0) {
      historyListContainer.innerHTML = `
        <div style="text-align: center; padding: 48px 16px; color: var(--text-muted);">
          <svg viewBox="0 0 24 24" style="width: 36px; height: 36px; fill: currentColor; margin-bottom: 8px; opacity: 0.5;"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-2 10H7v-2h10v2z"/></svg>
          <p style="font-weight: 500;">No se encontraron dictados</p>
          <p style="font-size: 12px; margin-top: 4px;">Usa el atajo de teclado para dictar en cualquier programa.</p>
        </div>
      `;
      return;
    }

    filtered.forEach(item => {
      const card = document.createElement('div');
      card.className = 'history-card';

      const isOk = item.paste_success !== false;
      const badgeClass = isOk ? 'success' : 'clipboard';
      const badgeText = isOk ? 'Pegado exitoso' : 'En portapapeles';

      const wpmStr = item.wpm ? `${Math.round(item.wpm)} WPM` : '';
      const durStr = item.duration_sec ? `${item.duration_sec.toFixed(1)}s` : '';
      const wordsStr = item.word_count ? `${item.word_count} palabras` : '';

      card.innerHTML = `
        <div class="history-header">
          <div class="history-meta">
            <span>${formatRelativeTime(item.timestamp)}</span>
            ${wpmStr ? `<span>·</span> <span>${wpmStr}</span>` : ''}
            ${durStr ? `<span>·</span> <span>${durStr}</span>` : ''}
            ${wordsStr ? `<span>·</span> <span>${wordsStr}</span>` : ''}
          </div>
          <span class="history-badge ${badgeClass}">${badgeText}</span>
        </div>
        <div class="history-text">${escapeHtml(item.text)}</div>
        <div class="history-actions">
          <button class="action-chip-btn btn-copy" data-id="${item.id}">
            <svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
            Copiar
          </button>
          <button class="action-chip-btn btn-paste" data-id="${item.id}">
            <svg viewBox="0 0 24 24"><path d="M19 2h-4.18C14.4.84 13.3 0 12 0c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm7 18H5V4h2v3h10V4h2v16z"/></svg>
            Re-pegar
          </button>
          <button class="action-chip-btn btn-delete" data-id="${item.id}" style="color: var(--accent-red);">
            <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          </button>
        </div>
      `;

      // Copy Action
      card.querySelector('.btn-copy').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        if (bridge) {
          bridge.copyToClipboard(item.text);
        } else {
          navigator.clipboard.writeText(item.text);
        }
        btn.innerHTML = `<svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:#10b981;"><path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"/></svg> ¡Copiado!`;
        setTimeout(() => {
          btn.innerHTML = `<svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg> Copiar`;
        }, 1500);
      });

      // Re-paste Action
      card.querySelector('.btn-paste').addEventListener('click', () => {
        if (bridge) {
          bridge.reinjectTranscription(item.text);
        }
      });

      // Delete Action
      card.querySelector('.btn-delete').addEventListener('click', () => {
        if (bridge) {
          bridge.deleteHistoryItem(item.id, () => fetchHistory());
        }
      });

      historyListContainer.appendChild(card);
    });
  }

  function fetchHistory() {
    if (!bridge) return;
    bridge.getHistory(100, (jsonStr) => {
      try {
        const items = JSON.parse(jsonStr);
        renderHistory(items);
      } catch (err) {
        console.error('Error parseando historial:', err);
      }
    });
  }

  if (historySearchInput) {
    historySearchInput.addEventListener('input', () => {
      renderHistory(historyCache);
    });
  }

  if (btnRefreshHistory) {
    btnRefreshHistory.addEventListener('click', fetchHistory);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
  }

  // 4. Audio Level (VU Meter)
  function updateAudioLevel(level) {
    if (!soundVuBar) return;
    const clamped = Math.max(0, Math.min(1, level));
    soundVuBar.style.width = `${clamped * 100}%`;
    if (clamped > 0.8) {
      soundVuBar.style.backgroundColor = 'var(--accent-red)';
    } else if (clamped > 0.5) {
      soundVuBar.style.backgroundColor = 'var(--accent-amber)';
    } else {
      soundVuBar.style.backgroundColor = 'var(--accent-green)';
    }
    const db = clamped > 0 ? Math.round(20 * Math.log10(clamped)) : -60;
    if (soundDbLabel) soundDbLabel.textContent = `${db} dB`;
  }

  // 5. Config Sync
  function loadConfig() {
    if (!bridge) return;
    bridge.getConfig((jsonStr) => {
      try {
        const cfg = JSON.parse(jsonStr);
        const autostartEl = document.getElementById('cfgAutostart');
        const autoCopyEl = document.getElementById('cfgAutoCopy');
        const autoPauseEl = document.getElementById('cfgAutoPauseMedia');
        const hotkeyChipHome = document.getElementById('homeHotkeyChip');
        const hotkeyChipCfg = document.getElementById('cfgHotkeyChip');

        if (autostartEl) autostartEl.checked = !!cfg.autostart;
        if (autoCopyEl) autoCopyEl.checked = !!cfg.auto_copy_clipboard;
        if (autoPauseEl) autoPauseEl.checked = !!cfg.auto_pause_media;
        if (hotkeyChipHome && cfg.hotkey) hotkeyChipHome.textContent = cfg.hotkey.toUpperCase();
        if (hotkeyChipCfg && cfg.hotkey) hotkeyChipCfg.textContent = cfg.hotkey.toUpperCase();
      } catch (err) {
        console.error('Error cargando configuración:', err);
      }
    });
  }

  // Config toggles
  ['cfgAutostart', 'cfgAutoCopy', 'cfgAutoPauseMedia'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', () => {
        if (bridge) {
          bridge.saveConfigSetting(id, el.checked);
        }
      });
    }
  });

  // Theme toggle
  if (cfgThemeDark) {
    cfgThemeDark.addEventListener('change', (e) => {
      document.documentElement.setAttribute('data-theme', e.target.checked ? 'dark' : 'light');
    });
  }

  // Start recording action button in Home
  const itemStartRecording = document.getElementById('itemStartRecording');
  if (itemStartRecording) {
    itemStartRecording.addEventListener('click', () => {
      if (bridge) bridge.toggleDictation();
    });
  }

  // 6. Dashboard Metrics
  function fetchDashboardMetrics() {
    if (!bridge) return;
    bridge.getDashboardMetrics((jsonStr) => {
      try {
        const m = JSON.parse(jsonStr);
        const statWpm = document.getElementById('statWpm');
        const statWords = document.getElementById('statWords');
        const statApps = document.getElementById('statApps');
        const statTimeSaved = document.getElementById('statTimeSaved');

        if (statWpm) statWpm.textContent = m.avg_wpm || 0;
        if (statWords) statWords.textContent = (m.total_words || 0).toLocaleString();
        if (statApps) statApps.textContent = m.total_dictations || 0;
        if (statTimeSaved) statTimeSaved.textContent = m.minutes_saved || 0;
      } catch (err) {
        console.error('Error cargando métricas:', err);
      }
    });
  }

  // 7. Vocabulary Controller
  const vocabListContainer = document.getElementById('vocabListContainer');
  const vocabWordInput = document.getElementById('vocabWordInput');
  const vocabReplaceInput = document.getElementById('vocabReplaceInput');
  const btnAddVocab = document.getElementById('btnAddVocab');

  function fetchVocabulary() {
    if (!bridge || !vocabListContainer) return;
    bridge.getVocabulary((jsonStr) => {
      try {
        const items = JSON.parse(jsonStr);
        renderVocabulary(items);
      } catch (err) {
        console.error('Error cargando vocabulario:', err);
      }
    });
  }

  function renderVocabulary(items) {
    if (!vocabListContainer) return;
    vocabListContainer.innerHTML = '';
    if (!items || items.length === 0) {
      vocabListContainer.innerHTML = `
        <div style="text-align: center; padding: 32px 16px; color: var(--text-muted);">
          No hay términos de vocabulario registrados.
        </div>
      `;
      return;
    }

    items.forEach(item => {
      const row = document.createElement('div');
      row.className = 'list-card-item';
      const repLabel = item.replacement ? `<span style="font-weight: normal; color: var(--accent-blue);"> &rarr; ${escapeHtml(item.replacement)}</span>` : '';
      row.innerHTML = `
        <div class="item-left">
          <div class="item-text">
            <h4>${escapeHtml(item.word)}${repLabel}</h4>
            <p>${item.replacement ? 'Sustitución automática' : 'Término prioritario en contexto de LLM'}</p>
          </div>
        </div>
        <button class="action-chip-btn btn-del-vocab" data-id="${item.id}" style="color: var(--accent-red);">
          <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          Eliminar
        </button>
      `;

      row.querySelector('.btn-del-vocab').addEventListener('click', () => {
        if (bridge) {
          bridge.deleteVocabulary(item.id, () => fetchVocabulary());
        }
      });

      vocabListContainer.appendChild(row);
    });
  }

  if (btnAddVocab) {
    btnAddVocab.addEventListener('click', () => {
      const word = (vocabWordInput.value || '').trim();
      const rep = (vocabReplaceInput.value || '').trim();
      if (!word) return;

      if (bridge) {
        bridge.addVocabulary(word, rep, () => {
          vocabWordInput.value = '';
          vocabReplaceInput.value = '';
          fetchVocabulary();
        });
      }
    });
  }

  // 8. Modes Controller
  const modesContainer = document.querySelector('#view-modes .list-group');
  const btnCreateMode = document.getElementById('btnCreateMode');

  function fetchModes() {
    if (!bridge || !modesContainer) return;
    bridge.getModes((jsonStr) => {
      try {
        const modes = JSON.parse(jsonStr);
        renderModes(modes);
      } catch (err) {
        console.error('Error cargando modos:', err);
      }
    });
  }

  function renderModes(modes) {
    if (!modesContainer) return;
    modesContainer.innerHTML = '';

    modes.forEach(mode => {
      const card = document.createElement('div');
      card.className = 'list-card-item';
      const isActive = !!mode.active;
      const dot = isActive ? '<span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--accent-green); margin-left: 4px;"></span>' : '';

      card.innerHTML = `
        <div class="item-left">
          <div class="item-icon-circle" style="color: ${isActive ? 'var(--accent-green)' : 'var(--text-secondary)'};">
            <svg viewBox="0 0 24 24"><path d="M12 2L9.5 8.5 3 11l6.5 2.5L12 20l2.5-6.5L21 11l-6.5-2.5z"/></svg>
          </div>
          <div class="item-text">
            <h4>${escapeHtml(mode.name)} ${dot}</h4>
            <p>${escapeHtml(mode.description || '')}</p>
          </div>
        </div>
        ${isActive
          ? '<span class="action-chip-btn" style="color: var(--accent-green); font-weight: 600;">Activo</span>'
          : `<button class="btn-secondary btn-select-mode" data-id="${mode.id}" style="padding: 4px 12px; font-size: 12px;">Seleccionar</button>`
        }
      `;

      const selBtn = card.querySelector('.btn-select-mode');
      if (selBtn) {
        selBtn.addEventListener('click', () => {
          if (bridge) {
            bridge.setActiveMode(mode.id, () => fetchModes());
          }
        });
      }

      modesContainer.appendChild(card);
    });
  }

  if (btnCreateMode) {
    btnCreateMode.addEventListener('click', () => {
      const name = prompt('Nombre del nuevo modo:');
      if (!name) return;
      const desc = prompt('Descripción breve:') || '';
      const promptText = prompt('Instrucciones para el LLM (System Prompt):') || '';
      if (bridge) {
        bridge.createMode(name, desc, promptText, false, () => fetchModes());
      }
    });
  }

  // 9. Connect to Qt WebChannel
  function initWebChannel() {
    if (typeof QWebChannel === 'undefined') {
      console.warn('QWebChannel no detectado en el entorno. Modo standalone.');
      return;
    }

    new QWebChannel(qt.webChannelTransport, function (channel) {
      bridge = channel.objects.bridge;
      window.bridge = bridge;

      // Connect Signals
      if (bridge.historyUpdated) {
        bridge.historyUpdated.connect((jsonStr) => {
          try {
            renderHistory(JSON.parse(jsonStr));
            fetchDashboardMetrics();
          } catch (e) {
            console.error(e);
          }
        });
      }

      if (bridge.audioLevelChanged) {
        bridge.audioLevelChanged.connect(updateAudioLevel);
      }

      if (bridge.deviceListChanged) {
        bridge.deviceListChanged.connect((jsonStr, selectedKey) => {
          try {
            renderDevices(JSON.parse(jsonStr), selectedKey);
          } catch (e) {
            console.error(e);
          }
        });
      }

      // Initial calls
      bridge.listAudioDevices((jsonStr, selectedKey) => {
        try {
          renderDevices(JSON.parse(jsonStr), selectedKey);
        } catch (e) {
          console.error(e);
        }
      });

      fetchHistory();
      fetchDashboardMetrics();
      fetchVocabulary();
      fetchModes();
      loadConfig();
    });
  }

  document.addEventListener('DOMContentLoaded', initWebChannel);
})();
