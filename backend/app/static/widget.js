  /* Iveri AI Customer Support Widget v1.1.0 - Verified Callback Handover */
let lastUserQuery = '';
function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, function(m) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m];
  });
}
(function () {
  // Find script element and extract configuration
  const currentScript = document.currentScript || (function() {
    const scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  })();

  const businessSlug = currentScript ? (currentScript.getAttribute('data-business') || '') : '';
  
  // Auto-detect backend API origin from script source URL if not explicitly provided
  let scriptOrigin = window.location.origin;
  try {
    if (currentScript && currentScript.src) {
      scriptOrigin = new URL(currentScript.src, window.location.href).origin;
    }
  } catch(e) {}

  const apiBaseUrl = (currentScript && currentScript.getAttribute('data-api')) || scriptOrigin;

  if (!businessSlug) {
    console.error('[Iveri Widget] Missing data-business attribute.');
    return;
  }

  let sessionId = null;
  let businessData = {
    name: 'Customer Support',
    brand_color: '#4F46E5',
    starter_questions: []
  };

  // Inject Pure Lumina Light CSS Styles
  const style = document.createElement('style');
  style.innerHTML = `
    @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    .iveri-widget-bubble {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.4), 0 4px 6px -2px rgba(79, 70, 229, 0.2);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 999999;
      transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s ease;
      background-color: #4F46E5;
      color: white;
    }
    .iveri-widget-bubble:hover {
      transform: scale(1.06);
      box-shadow: 0 14px 28px -5px rgba(79, 70, 229, 0.5);
    }
    .iveri-widget-window {
      position: fixed;
      bottom: 92px;
      right: 24px;
      width: 380px;
      height: 580px;
      max-width: calc(100vw - 32px);
      max-height: calc(100vh - 110px);
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 20px;
      box-shadow: 0 20px 40px -10px rgba(15, 23, 42, 0.15), 0 8px 16px -4px rgba(15, 23, 42, 0.08);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 999999;
      font-family: 'Geist', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #0F172A;
    }
    .iveri-widget-header {
      padding: 14px 18px;
      background: #FFFFFF;
      border-bottom: 1px solid #E2E8F0;
      color: #0F172A;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .iveri-widget-messages {
      flex: 1;
      padding: 16px;
      overflow-y: auto;
      background: #F8FAFC;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .iveri-msg {
      max-width: 86%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 13.5px;
      line-height: 1.5;
      word-break: break-word;
    }
    .iveri-msg-user {
      align-self: flex-end;
      background: #4F46E5;
      color: #FFFFFF;
      border: none;
      border-bottom-right-radius: 4px;
      box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);
    }
    .iveri-msg-assistant {
      align-self: flex-start;
      background: #FFFFFF;
      color: #0F172A;
      border: 1px solid #E2E8F0;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    .iveri-citation-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-top: 6px;
      padding: 3px 8px;
      background: #ECFDF5;
      color: #047857;
      border-radius: 6px;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 500;
      border: 1px solid #A7F3D0;
      cursor: pointer;
      transition: background 0.15s;
    }
    .iveri-citation-badge:hover {
      background: #D1FAE5;
    }
    .iveri-feedback-row {
      display: flex;
      gap: 6px;
      margin-top: 6px;
      align-items: center;
    }
    .iveri-feedback-btn {
      background: #F8FAFC;
      border: 1px solid #E2E8F0;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
      padding: 2px 6px;
      color: #64748B;
      transition: all 0.15s;
    }
    .iveri-feedback-btn:hover {
      color: #0F172A;
      border-color: #CBD5E1;
      background: #F1F5F9;
    }
    .iveri-starters {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }
    .iveri-starter-pill {
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 8px;
      padding: 5px 10px;
      font-size: 12px;
      color: #334155;
      cursor: pointer;
      transition: all 0.15s;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    }
    .iveri-starter-pill:hover {
      background: #F8FAFC;
      border-color: #4F46E5;
      color: #4F46E5;
    }
    .iveri-input-box {
      padding: 12px 14px;
      background: #FFFFFF;
      border-top: 1px solid #E2E8F0;
      display: flex;
      gap: 8px;
    }
    .iveri-input {
      flex: 1;
      background: #F8FAFC;
      color: #0F172A;
      border: 1px solid #CBD5E1;
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13.5px;
      outline: none;
      transition: border 0.15s, background 0.15s;
    }
    .iveri-input:focus {
      background: #FFFFFF;
      border-color: #4F46E5;
      box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.15);
    }
    .iveri-send-btn {
      background: #4F46E5;
      color: white;
      border: none;
      border-radius: 8px;
      padding: 8px 14px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
      transition: background 0.15s;
      box-shadow: 0 1px 2px rgba(79, 70, 229, 0.2);
    }
    .iveri-send-btn:hover {
      background: #4338CA;
    }
    @media (max-width: 640px) {
      .iveri-widget-bubble {
        bottom: 16px;
        right: 16px;
        width: 50px;
        height: 50px;
      }
      .iveri-widget-window {
        bottom: 0 !important;
        right: 0 !important;
        left: 0 !important;
        top: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        height: 100dvh !important;
        max-width: 100vw !important;
        max-height: 100dvh !important;
        border-radius: 0 !important;
        border: none !important;
      }
      .iveri-input {
        font-size: 16px !important;
      }
    }
  `;
  document.head.appendChild(style);

  // Create Widget DOM
  const bubble = document.createElement('div');
  bubble.className = 'iveri-widget-bubble';
  bubble.innerHTML = `
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
    </svg>
  `;

  const chatWindow = document.createElement('div');
  chatWindow.className = 'iveri-widget-window';
  chatWindow.innerHTML = `
    <div class="iveri-widget-header" id="iveri-header">
      <div style="display:flex; align-items:center; gap:10px;">
        <div id="iveri-header-avatar" style="width:30px; height:30px; border-radius:50%; background:#EEF2FF; color:#4F46E5; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:13px; overflow:hidden;">
          <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#059669;"></span>
        </div>
        <div>
          <div style="font-weight: 600; font-size: 14px; color: #0F172A;" id="iveri-biz-name">Support Assistant</div>
          <div id="iveri-header-subtitle" style="font-size: 11px; font-family:'JetBrains Mono', monospace; color: #64748B;">Grounded RAG • Verified</div>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:6px;">
        <button id="iveri-cb-btn" title="Request Callback" style="display:none; background:#EEF2FF; border:1px solid #C7D2FE; color:#4F46E5; font-size:11px; font-weight:600; cursor:pointer; padding:3px 7px; border-radius:6px; align-items:center; gap:3px;">
          <span id="iveri-cb-icon">📞</span> <span id="iveri-cb-label">Callback</span>
        </button>
        <a id="iveri-wa-btn" title="Chat on WhatsApp" target="_blank" style="display:none; background:#ECFDF5; border:1px solid #A7F3D0; color:#059669; font-size:11px; font-weight:600; text-decoration:none; padding:3px 7px; border-radius:6px; align-items:center; gap:3px;">
          💬 WA
        </a>
        <button id="iveri-share-btn" title="Share Conversation" style="background:none; border:none; color:#64748B; font-size:14px; cursor:pointer; padding:4px; display:flex; align-items:center;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
        </button>
        <button style="background:none; border:none; color:#64748B; font-size:20px; cursor:pointer; padding:2px;" id="iveri-close">×</button>
      </div>
    </div>
    <div class="iveri-widget-messages" id="iveri-msgs">
      <div class="iveri-msg iveri-msg-assistant">
        Hello! How can I assist you today with store policies, orders, or products?
        <div class="iveri-starters" id="iveri-starter-container"></div>
      </div>
    </div>
    <div id="iveri-cb-modal" style="display:none; position:absolute; inset:0; background:rgba(15,23,42,0.6); backdrop-filter:blur(2px); z-index:50; padding:16px; align-items:center; justify-content:center;">
      <div style="background:#FFFFFF; border-radius:12px; padding:16px; width:100%; max-width:320px; box-shadow:0 10px 25px rgba(0,0,0,0.2); font-family:inherit;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <div id="iveri-cb-modal-title" style="font-weight:700; font-size:13px; color:#0F172A;">📞 Request Human Callback</div>
          <button id="iveri-cb-modal-close" style="background:none; border:none; font-size:18px; color:#94A3B8; cursor:pointer;">×</button>
        </div>
        <div id="iveri-cb-modal-sub" style="font-size:10.5px; color:#64748B; margin-bottom:10px; line-height:1.3;">
          Enter your contact info so our support team can reach you.
        </div>
        <div style="display:flex; flex-direction:column; gap:8px; font-size:11px;">
          <div id="iveri-cb-wa-direct" style="display:none; padding:8px; background:#F0FDF4; border:1px solid #BBF7D0; border-radius:8px; text-align:center;">
            <a id="iveri-cb-wa-link" href="#" target="_blank" style="display:inline-block; width:100%; box-sizing:border-box; background:#10B981; color:#FFFFFF; text-decoration:none; font-weight:700; padding:6px 10px; border-radius:6px; font-size:11px;">
              🟢 Open Direct WhatsApp Chat
            </a>
            <div style="font-size:9px; color:#64748B; margin-top:4px;">— OR REQUEST A WHATSAPP MESSAGE —</div>
          </div>
          <div>
            <label style="color:#475569; font-weight:600;">Your Name</label>
            <input type="text" id="iveri-cb-name" placeholder="e.g. John Doe" style="width:100%; box-sizing:border-box; padding:6px 8px; border:1px solid #CBD5E1; border-radius:6px; font-size:11px; margin-top:2px;" />
          </div>
          <div>
            <label id="iveri-cb-contact-label" style="color:#475569; font-weight:600;">Phone Number or Email *</label>
            <input type="text" id="iveri-cb-contact" placeholder="+91 98765 43210 or email" style="width:100%; box-sizing:border-box; padding:6px 8px; border:1px solid #CBD5E1; border-radius:6px; font-size:11px; margin-top:2px;" />
          </div>
          <div>
            <label id="iveri-cb-note-label" style="color:#475569; font-weight:600;">How can we help?</label>
            <textarea id="iveri-cb-note" rows="2" placeholder="Describe your inquiry..." style="width:100%; box-sizing:border-box; padding:6px 8px; border:1px solid #CBD5E1; border-radius:6px; font-size:11px; margin-top:2px;"></textarea>
          </div>
          <button id="iveri-cb-submit" style="background:#4F46E5; color:#FFFFFF; border:none; padding:8px; border-radius:6px; font-weight:600; cursor:pointer; margin-top:4px;">Submit Callback Request</button>
        </div>
      </div>
    </div>
    <div class="iveri-input-box">
      <input type="text" class="iveri-input" id="iveri-input" placeholder="Ask a question..." />
      <button class="iveri-send-btn" id="iveri-send">Send</button>
    </div>
  `;

  document.body.appendChild(bubble);
  document.body.appendChild(chatWindow);

  // Toggle Visibility
  bubble.onclick = () => {
    chatWindow.style.display = chatWindow.style.display === 'flex' ? 'none' : 'flex';
    if (chatWindow.style.display === 'flex') {
      initSession();
      document.getElementById('iveri-input').focus();
    }
  };

  document.getElementById('iveri-close').onclick = () => {
    chatWindow.style.display = 'none';
  };

  function hexToRgba(hex, alpha) {
    if (!hex) return `rgba(79, 70, 229, ${alpha})`;
    let c = String(hex).replace('#', '').trim();
    if (c.length === 3) c = c.split('').map(x => x + x).join('');
    if (c.length !== 6) return `rgba(79, 70, 229, ${alpha})`;
    const num = parseInt(c, 16);
    return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
  }

  function getContrastColor(hex) {
    if (!hex) return '#FFFFFF';
    let c = String(hex).replace('#', '').trim();
    if (c.length === 3) c = c.split('').map(x => x + x).join('');
    if (c.length !== 6) return '#FFFFFF';
    const r = parseInt(c.substr(0, 2), 16);
    const g = parseInt(c.substr(2, 2), 16);
    const b = parseInt(c.substr(4, 2), 16);
    const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
    return (yiq >= 170) ? '#0F172A' : '#FFFFFF';
  }

  function applyBrandTheme(color) {
    if (!color) return;
    businessData.brand_color = color;
    const textColor = getContrastColor(color);
    const isDark = (textColor === '#FFFFFF');

    // 1. Header Styling — Matches the Studio Real-Time Preview
    const header = document.getElementById('iveri-header');
    if (header) {
      header.style.backgroundColor = color;
      header.style.color = textColor;
      header.style.borderBottom = 'none';
    }
    const bizName = document.getElementById('iveri-biz-name');
    if (bizName) bizName.style.color = textColor;

    const subTitle = document.getElementById('iveri-header-subtitle');
    if (subTitle) subTitle.style.color = isDark ? 'rgba(255, 255, 255, 0.85)' : 'rgba(15, 23, 42, 0.75)';

    const closeBtn = document.getElementById('iveri-close');
    if (closeBtn) {
      closeBtn.style.color = textColor;
      closeBtn.style.opacity = '0.9';
    }

    const shareBtn = document.getElementById('iveri-share-btn');
    if (shareBtn) {
      shareBtn.style.color = textColor;
      shareBtn.style.opacity = '0.9';
    }

    // Header Callback Button (translucent frosted pill like in Studio Preview)
    const cbBtn = document.getElementById('iveri-cb-btn');
    if (cbBtn) {
      cbBtn.style.background = isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(15, 23, 42, 0.08)';
      cbBtn.style.border = isDark ? '1px solid rgba(255, 255, 255, 0.35)' : '1px solid rgba(15, 23, 42, 0.2)';
      cbBtn.style.color = textColor;
    }

    // Header WhatsApp Button
    const waBtn = document.getElementById('iveri-wa-btn');
    if (waBtn) {
      waBtn.style.background = isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(15, 23, 42, 0.08)';
      waBtn.style.border = isDark ? '1px solid rgba(255, 255, 255, 0.35)' : '1px solid rgba(15, 23, 42, 0.2)';
      waBtn.style.color = textColor;
    }

    // Header Avatar fallback bg
    const headerAvatar = document.getElementById('iveri-header-avatar');
    if (headerAvatar && !headerAvatar.querySelector('img')) {
      headerAvatar.style.background = isDark ? 'rgba(255, 255, 255, 0.25)' : 'rgba(15, 23, 42, 0.12)';
      headerAvatar.style.color = textColor;
    }

    // 2. Bubble Launcher
    if (bubble) {
      bubble.style.backgroundColor = color;
      bubble.style.boxShadow = `0 10px 25px -5px ${hexToRgba(color, 0.45)}, 0 4px 6px -2px ${hexToRgba(color, 0.25)}`;
    }

    // 3. Send Button
    const sendBtn = document.getElementById('iveri-send');
    if (sendBtn) {
      sendBtn.style.backgroundColor = color;
      sendBtn.style.color = textColor;
      sendBtn.style.boxShadow = `0 2px 6px ${hexToRgba(color, 0.35)}`;
    }

    // 4. Callback Submit Button
    const cbSubmit = document.getElementById('iveri-cb-submit');
    if (cbSubmit) {
      cbSubmit.style.backgroundColor = color;
      cbSubmit.style.color = textColor;
    }

    // 5. Dynamic CSS rules for user messages, input focus, hover states
    let themeStyle = document.getElementById('iveri-dynamic-theme-styles');
    if (!themeStyle) {
      themeStyle = document.createElement('style');
      themeStyle.id = 'iveri-dynamic-theme-styles';
      document.head.appendChild(themeStyle);
    }
    themeStyle.innerHTML = `
      .iveri-msg-user {
        background: ${color} !important;
        color: ${textColor} !important;
        box-shadow: 0 2px 6px ${hexToRgba(color, 0.3)} !important;
      }
      .iveri-input:focus {
        border-color: ${color} !important;
        box-shadow: 0 0 0 2px ${hexToRgba(color, 0.2)} !important;
      }
      .iveri-send-btn:hover {
        filter: brightness(0.92);
      }
      .iveri-starter-pill:hover {
        border-color: ${color} !important;
        color: ${color} !important;
      }
    `;
  }

  // Fetch Public Business Profile
  fetch(`${apiBaseUrl}/api/public/business/${businessSlug}`)
    .then(r => r.json())
    .then(data => {
      businessData = data;
      applyBrandTheme(data.brand_color || '#4F46E5');

      if (data.widget_position === 'bottom-left') {
        bubble.style.left = '24px';
        bubble.style.right = 'auto';
        chatWindow.style.left = '24px';
        chatWindow.style.right = 'auto';
      }

      if (data.avatar_url) {
        bubble.innerHTML = `<img src="${data.avatar_url}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;" alt="Avatar">`;
        document.getElementById('iveri-header-avatar').innerHTML = `<img src="${data.avatar_url}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;" alt="Avatar">`;
      }

      if (data.welcome_message) {
        const welcomeBubble = document.querySelector('.iveri-msg.iveri-msg-assistant');
        if (welcomeBubble) {
          welcomeBubble.innerHTML = `${formatContent(data.welcome_message)}<div class="iveri-starters" id="iveri-starter-container"></div>`;
        }
      }

      document.getElementById('iveri-biz-name').innerText = data.name || 'Support Assistant';

      // Callback Button (channel-aware icon and label)
      if (data.enable_callback !== false) {
        const cbBtn = document.getElementById('iveri-cb-btn');
        if (cbBtn) {
          cbBtn.style.display = 'flex';
          const ch = data.callback_channel || 'phone_and_email';
          let icon = '📞';
          let defLabel = 'Callback';
          if (ch === 'phone') {
            icon = '📞';
            defLabel = 'Call Me';
          } else if (ch === 'email') {
            icon = '✉️';
            defLabel = 'Email Us';
          } else if (ch === 'whatsapp') {
            icon = '💬';
            defLabel = 'WhatsApp';
          }
          const iconEl = document.getElementById('iveri-cb-icon');
          const labelEl = document.getElementById('iveri-cb-label');
          if (iconEl) iconEl.innerText = icon;
          if (labelEl) labelEl.innerText = data.callback_button_text || defLabel;
          cbBtn.onclick = () => openWidgetCallbackModal();
        }
      } else {
        const cbBtn = document.getElementById('iveri-cb-btn');
        if (cbBtn) cbBtn.style.display = 'none';
      }

      // WhatsApp Button
      if (data.whatsapp_number) {
        const cleanWa = data.whatsapp_number.replace(/[^0-9]/g, '');
        const waBtn = document.getElementById('iveri-wa-btn');
        if (waBtn) {
          waBtn.style.display = 'flex';
          waBtn.href = `https://wa.me/${cleanWa}?text=Hi%2C%20I%20have%20an%20inquiry%20regarding%20${encodeURIComponent(data.name || 'your store')}`;
        }
      }
      
      const starterContainer = document.getElementById('iveri-starter-container');
      if (starterContainer) {
        starterContainer.innerHTML = '';
        if (data.starter_questions && data.starter_questions.length > 0) {
          starterContainer.style.display = 'flex';
          data.starter_questions.forEach(q => {
            const pill = document.createElement('button');
            pill.className = 'iveri-starter-pill';
            pill.innerText = q;
            pill.onclick = () => sendMessage(q);
            starterContainer.appendChild(pill);
          });
        } else {
          starterContainer.style.display = 'none';
        }
      }
    })
    .catch(err => console.warn('[Iveri Widget] Failed to load business branding:', err));

  document.getElementById('iveri-share-btn').onclick = () => {
    if (!sessionId) {
      alert("Please send a question before sharing this conversation.");
      return;
    }
    const shareUrl = `${apiBaseUrl}/share/${sessionId}`;
    navigator.clipboard.writeText(shareUrl);
    alert(`Conversation link copied to clipboard!\n${shareUrl}`);
  };

  // Initialize Session (returns Promise)
  function initSession() {
    if (sessionId) return Promise.resolve(sessionId);
    return fetch(`${apiBaseUrl}/api/chat/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ business_slug_or_token: businessSlug, channel: 'widget' })
    })
      .then(r => r.json())
      .then(d => { sessionId = d.id; return sessionId; })
      .catch(e => { console.error('[Iveri Widget] Session init failed:', e); return null; });
  }

  // Helper to format content
  function formatContent(text) {
    if (!text) return '';
    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/^• (.*$)/gm, '<div style="margin-left: 8px;">• $1</div>')
      .replace(/^- (.*$)/gm, '<div style="margin-left: 8px;">• $1</div>')
      .replace(/\n\n/g, '<div style="height:6px;"></div>')
      .replace(/\n/g, '<br/>');
  }

  // Send Message
  async function sendMessage(text) {
    if (!text || (typeof text === 'string' && !text.trim())) return;
    const msgText = text.trim();
    if (!sessionId) {
      await initSession();
    }
    const msgsContainer = document.getElementById('iveri-msgs');

    // Append User Message
    lastUserQuery = text;
    const userBubble = document.createElement('div');
    userBubble.className = 'iveri-msg iveri-msg-user';
    userBubble.innerText = msgText;
    msgsContainer.appendChild(userBubble);
    msgsContainer.scrollTop = msgsContainer.scrollHeight;

    // Append Assistant Loading Indicator
    const botBubble = document.createElement('div');
    botBubble.className = 'iveri-msg iveri-msg-assistant';
    botBubble.innerText = 'Retrieving verified documents...';
    msgsContainer.appendChild(botBubble);
    msgsContainer.scrollTop = msgsContainer.scrollHeight;

    fetch(`${apiBaseUrl}/api/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: msgText })
    })
      .then(r => r.json())
      .then(data => {
        botBubble.innerHTML = `<div>${formatContent(data.content)}</div>`;

        // Citations
        if (data.citations && data.citations.length > 0) {
          const citeRow = document.createElement('div');
          citeRow.style.marginTop = '4px';
          citeRow.style.display = 'flex';
          citeRow.style.flexWrap = 'wrap';
          citeRow.style.gap = '4px';
          data.citations.forEach(c => {
            const badge = document.createElement('span');
            badge.className = 'iveri-citation-badge';
            badge.innerText = `📄 ${c.document_name} (p.${c.page_number})`;
            badge.title = `${c.document_name} (Page ${c.page_number}) - Click to view highlighted PDF source`;
            badge.style.cursor = 'pointer';
            badge.onclick = () => {
              if (c.chunk_id) {
                window.open(`${apiBaseUrl}/api/chat/citation/${encodeURIComponent(c.chunk_id)}/page-preview?query=${encodeURIComponent(lastUserQuery || '')}`, '_blank');
              } else if (c.document_id) {
                window.open(`${apiBaseUrl}/api/chat/document/${c.document_id}/file#page=${c.page_number}`, '_blank');
              } else {
                alert(`Source: ${c.document_name} (Page ${c.page_number})\n\nExcerpt:\n${c.excerpt}`);
              }
            };
            citeRow.appendChild(badge);
          });
          botBubble.appendChild(citeRow);
        }

        // Thumbs Up / Down
        const now = new Date();
        const timeStampStr = `${now.toLocaleDateString([], {month:'short', day:'numeric'})} ${now.toLocaleTimeString([], {hour:'numeric', minute:'2-digit', hour12:true})}`;
        const feedbackRow = document.createElement('div');
        feedbackRow.className = 'iveri-feedback-row';
        feedbackRow.innerHTML = `
          <button class="iveri-feedback-btn" title="Helpful">👍</button>
          <button class="iveri-feedback-btn" title="Not helpful">👎</button>
          <span style="font-size:10px; font-family:'JetBrains Mono',monospace; color:#94A3B8; margin-left:auto;">${timeStampStr} • ${data.latency_ms}ms</span>
        `;
        const buttons = feedbackRow.querySelectorAll('button');
        buttons[0].onclick = () => sendFeedback(data.id, 'up', feedbackRow);
        buttons[1].onclick = () => sendFeedback(data.id, 'down', feedbackRow);
        botBubble.appendChild(feedbackRow);

        // Enhanced Human Handoff / Callback Card if unknown
        if (!data.is_answered) {
          const leadBox = document.createElement('div');
          leadBox.style.marginTop = '8px';
          leadBox.style.padding = '10px';
          leadBox.style.background = 'linear-gradient(to right, #FFFBEB, #EEF2FF)';
          leadBox.style.border = '1px solid #FDE68A';
          leadBox.style.borderRadius = '10px';
          
          let waBtnHtml = '';
          if (businessData && businessData.whatsapp_number) {
            const cleanWa = businessData.whatsapp_number.replace(/[^0-9]/g, '');
            waBtnHtml = `<a href="https://wa.me/${cleanWa}?text=Hi%2C%20I%20have%20an%20inquiry%20regarding%20${encodeURIComponent(businessData.name || 'your store')}" target="_blank" style="background:#059669; color:#FFFFFF; text-decoration:none; padding:5px 9px; font-size:11px; border-radius:6px; font-weight:600; display:inline-flex; align-items:center; gap:3px;">💬 WhatsApp</a>`;
          }

          leadBox.innerHTML = `
            <div style="font-size:11.5px; color:#1E293B; font-weight:700; margin-bottom:4px;">Need team follow-up or callback?</div>
            <div style="font-size:11px; color:#64748B; margin-bottom:8px;">Our team can contact you via phone, email, or WhatsApp.</div>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              <button class="iveri-cb-handoff-btn" style="background:#4F46E5; color:#FFFFFF; border:none; padding:5px 10px; font-size:11px; border-radius:6px; font-weight:600; cursor:pointer; display:inline-flex; align-items:center; gap:3px;">📞 Request Callback</button>
              ${waBtnHtml}
            </div>
          `;
          
          const cbBtn = leadBox.querySelector('.iveri-cb-handoff-btn');
          if (cbBtn) {
            cbBtn.onclick = () => openWidgetCallbackModal();
          }
          botBubble.appendChild(leadBox);
        }

        msgsContainer.scrollTop = msgsContainer.scrollHeight;
      })
      .catch(e => {
        botBubble.innerText = "Sorry, I am having trouble connecting right now. Please try again in a moment.";
      });
  }

  function sendFeedback(msgId, vote, rowEl) {
    fetch(`${apiBaseUrl}/api/chat/message/${msgId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback: vote })
    }).then(() => {
      rowEl.innerHTML = `<span style="font-size:11px; font-family:'JetBrains Mono',monospace; color:${vote==='up'?'#059669':'#DC2626'}; font-weight:500;">Feedback recorded (${vote === 'up' ? '✓' : '✕'})</span>`;
    });
  }

  // Bind Enter key
  const inputEl = document.getElementById('iveri-input');
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const val = inputEl.value;
      inputEl.value = '';
      sendMessage(val);
    }
  });

  document.getElementById('iveri-send').onclick = () => {
    const val = inputEl.value;
    inputEl.value = '';
    sendMessage(val);
  };

  // ==========================================
  // Dynamic Channel Handover & Callback Logic
  // ==========================================
  function renderCallbackModalForChannel(channel, data) {
    const titleEl = document.getElementById('iveri-cb-modal-title');
    const subEl = document.getElementById('iveri-cb-modal-sub');
    const contactLabel = document.getElementById('iveri-cb-contact-label');
    const contactInput = document.getElementById('iveri-cb-contact');
    const noteLabel = document.getElementById('iveri-cb-note-label');
    const noteInput = document.getElementById('iveri-cb-note');
    const submitBtn = document.getElementById('iveri-cb-submit');
    const waDirect = document.getElementById('iveri-cb-wa-direct');
    const waLink = document.getElementById('iveri-cb-wa-link');

    const ch = channel || (data && data.callback_channel) || 'phone_and_email';

    if (ch === 'phone') {
      if (titleEl) titleEl.innerText = '📞 Request Phone Callback';
      if (subEl) subEl.innerText = 'Leave your mobile number for a fast callback from our team.';
      if (contactLabel) contactLabel.innerText = 'Phone / Mobile Number *';
      if (contactInput) {
        contactInput.type = 'tel';
        contactInput.placeholder = 'e.g. +91 98765 43210 or (555) 019-2834';
      }
      if (noteLabel) noteLabel.innerText = 'Topic or Reason for Call (Optional)';
      if (noteInput) noteInput.placeholder = 'Briefly tell us what you need assistance with...';
      if (submitBtn) submitBtn.innerText = 'Request Phone Call';
      if (waDirect) waDirect.style.display = 'none';
    } else if (ch === 'email') {
      if (titleEl) titleEl.innerText = '✉️ Request Email Follow-Up';
      if (subEl) subEl.innerText = 'Send your question directly to our support team email inbox.';
      if (contactLabel) contactLabel.innerText = 'Email Address *';
      if (contactInput) {
        contactInput.type = 'email';
        contactInput.placeholder = 'e.g. yourname@company.com';
      }
      if (noteLabel) noteLabel.innerText = 'Your Inquiry or Message *';
      if (noteInput) noteInput.placeholder = 'Type your question or issue in detail...';
      if (submitBtn) submitBtn.innerText = 'Send Email Inquiry';
      if (waDirect) waDirect.style.display = 'none';
    } else if (ch === 'whatsapp') {
      if (titleEl) titleEl.innerText = '💬 Connect on WhatsApp';
      if (subEl) subEl.innerText = 'Chat directly with our support team or request a WhatsApp message.';
      if (contactLabel) contactLabel.innerText = 'Your WhatsApp Mobile Number *';
      if (contactInput) {
        contactInput.type = 'tel';
        contactInput.placeholder = 'e.g. +91 98765 43210';
      }
      if (noteLabel) noteLabel.innerText = 'What can we help you with?';
      if (noteInput) noteInput.placeholder = 'Describe your inquiry...';
      if (submitBtn) submitBtn.innerText = 'Request WhatsApp Message';

      if (data && data.whatsapp_number && waDirect && waLink) {
        const cleanWa = data.whatsapp_number.replace(/[^0-9]/g, '');
        waLink.href = `https://wa.me/${cleanWa}?text=Hi%2C%20I%20have%20an%20inquiry%20regarding%20${encodeURIComponent((data && data.name) || 'your store')}`;
        waDirect.style.display = 'block';
      } else if (waDirect) {
        waDirect.style.display = 'none';
      }
    } else {
      // Default: phone_and_email
      if (titleEl) titleEl.innerText = '📞 Request Human Callback';
      if (subEl) subEl.innerText = 'Enter your contact info so our support team can reach you.';
      if (contactLabel) contactLabel.innerText = 'Phone Number or Email Address *';
      if (contactInput) {
        contactInput.type = 'text';
        contactInput.placeholder = '+91 98765 43210 or email@domain.com';
      }
      if (noteLabel) noteLabel.innerText = 'How can we help?';
      if (noteInput) noteInput.placeholder = 'Describe your inquiry...';
      if (submitBtn) submitBtn.innerText = (data && data.callback_button_text) ? data.callback_button_text : 'Submit Callback Request';
      if (waDirect) waDirect.style.display = 'none';
    }
  }

  function openWidgetCallbackModal() {
    const modal = document.getElementById('iveri-cb-modal');
    if (!modal) return;
    renderCallbackModalForChannel((businessData && businessData.callback_channel) || 'phone_and_email', businessData);
    const noteEl = document.getElementById('iveri-cb-note');
    if (noteEl && !noteEl.value && lastUserQuery) {
      noteEl.value = 'Regarding inquiry: ' + lastUserQuery;
    }
    modal.style.display = 'flex';
    const contactInput = document.getElementById('iveri-cb-contact');
    if (contactInput) contactInput.focus();
  }

  function closeWidgetCallbackModal() {
    const modal = document.getElementById('iveri-cb-modal');
    if (modal) modal.style.display = 'none';
  }

  async function submitWidgetCallbackRequest() {
    const nameEl = document.getElementById('iveri-cb-name');
    const contactEl = document.getElementById('iveri-cb-contact');
    const noteEl = document.getElementById('iveri-cb-note');
    const submitBtn = document.getElementById('iveri-cb-submit');

    const name = nameEl ? nameEl.value.trim() : '';
    const contact = contactEl ? contactEl.value.trim() : '';
    const note = (noteEl ? noteEl.value.trim() : '') || lastUserQuery || 'General callback request';
    const ch = (businessData && businessData.callback_channel) || 'phone_and_email';

    if (!contact) {
      if (ch === 'phone') {
        alert('Please enter your phone number so our team can call you back.');
      } else if (ch === 'email') {
        alert('Please enter your email address so our team can reply to you.');
      } else if (ch === 'whatsapp') {
        alert('Please enter your WhatsApp mobile number.');
      } else {
        alert('Please enter your phone number or email address so we can reach you.');
      }
      if (contactEl) contactEl.focus();
      return;
    }

    if (ch === 'phone' && contact.replace(/\D/g, '').length < 7) {
      alert('Please enter a valid phone number (at least 7 digits with country/area code).');
      if (contactEl) contactEl.focus();
      return;
    }
    if (ch === 'email' && (!contact.includes('@') || !contact.includes('.'))) {
      alert('Please enter a valid email address (e.g. name@company.com).');
      if (contactEl) contactEl.focus();
      return;
    }
    if (ch === 'whatsapp' && contact.replace(/\D/g, '').length < 7) {
      alert('Please enter a valid WhatsApp mobile number (at least 7 digits with country code).');
      if (contactEl) contactEl.focus();
      return;
    }

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerText = 'Submitting Request...';
      submitBtn.style.opacity = '0.7';
    }

    try {
      if (!sessionId) {
        await initSession();
      }

      const res = await fetch(`${apiBaseUrl}/api/chat/contact-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId || null,
          business_slug: businessSlug,
          customer_name: name || null,
          customer_contact: contact,
          message: note,
          channel: 'widget'
        })
      });

      if (res.ok) {
        const data = await res.json();
        closeWidgetCallbackModal();

        // Clear inputs
        if (nameEl) nameEl.value = '';
        if (contactEl) contactEl.value = '';
        if (noteEl) noteEl.value = '';

        let confirmTitle = '✅ Callback Request Submitted!';
        let confirmBody = `Ticket <strong>#${data.ticket_number}</strong> created. Thank you${name ? ' ' + name : ''}! Our team has been notified with high priority and will contact you promptly at <strong>${contact}</strong>.`;

        if (ch === 'phone') {
          confirmTitle = '📞 Phone Callback Request Logged!';
          confirmBody = `Ticket <strong>#${data.ticket_number}</strong> created. Thank you${name ? ' ' + name : ''}! An agent has been notified and will call you at <strong>${contact}</strong>.`;
        } else if (ch === 'email') {
          confirmTitle = '✉️ Email Follow-Up Request Received!';
          confirmBody = `Inquiry <strong>#${data.ticket_number}</strong> received. Thank you${name ? ' ' + name : ''}! Our support team will reply to your email at <strong>${contact}</strong>.`;
        } else if (ch === 'whatsapp') {
          confirmTitle = '💬 WhatsApp Message Request Logged!';
          confirmBody = `Request <strong>#${data.ticket_number}</strong> logged. Thank you${name ? ' ' + name : ''}! Our support team will message you on WhatsApp at <strong>${contact}</strong>.`;
        }

        // Append confirmation card inside the chat messages container
        const msgsContainer = document.getElementById('iveri-msgs');
        const confirmBubble = document.createElement('div');
        confirmBubble.className = 'iveri-msg iveri-msg-assistant';
        confirmBubble.style.borderColor = '#A7F3D0';
        confirmBubble.style.background = '#F0FDF4';
        confirmBubble.innerHTML = `
          <div style="font-weight:700; color:#065F46; margin-bottom:4px; font-size:13px;">${confirmTitle}</div>
          <div style="font-size:12px; color:#166534; line-height:1.4;">
            ${confirmBody}
          </div>
        `;
        msgsContainer.appendChild(confirmBubble);
        msgsContainer.scrollTop = msgsContainer.scrollHeight;
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || 'Could not submit callback request. Please try again.');
      }
    } catch (err) {
      console.error('[Iveri Widget] Callback request failed:', err);
      alert('Network error submitting request. Please check your connection.');
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        const ch = (businessData && businessData.callback_channel) || 'phone_and_email';
        submitBtn.innerText = ch === 'phone' ? 'Request Phone Call' : (ch === 'email' ? 'Send Email Inquiry' : (ch === 'whatsapp' ? 'Request WhatsApp Message' : 'Submit Callback Request'));
        submitBtn.style.opacity = '1';
      }
    }
  }

  // Wire modal close and submit events
  const cbModalClose = document.getElementById('iveri-cb-modal-close');
  if (cbModalClose) {
    cbModalClose.onclick = closeWidgetCallbackModal;
  }
  const cbModal = document.getElementById('iveri-cb-modal');
  if (cbModal) {
    cbModal.onclick = (e) => {
      if (e.target === cbModal) closeWidgetCallbackModal();
    };
  }
  const cbSubmit = document.getElementById('iveri-cb-submit');
  if (cbSubmit) {
    cbSubmit.onclick = submitWidgetCallbackRequest;
  }

})();