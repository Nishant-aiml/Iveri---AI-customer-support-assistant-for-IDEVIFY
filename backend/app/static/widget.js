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
          <div style="font-size: 11px; font-family:'JetBrains Mono', monospace; color: #64748B;">Grounded RAG • Verified</div>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:6px;">
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

  // Fetch Public Business Profile
  fetch(`${apiBaseUrl}/api/public/business/${businessSlug}`)
    .then(r => r.json())
    .then(data => {
      businessData = data;
      if (data.brand_color && data.brand_color !== '#2563eb' && data.brand_color !== '#6366F1') {
        bubble.style.backgroundColor = data.brand_color;
        document.getElementById('iveri-send').style.backgroundColor = data.brand_color;
      }

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

  // Initialize Session
  function initSession() {
    if (sessionId) return;
    fetch(`${apiBaseUrl}/api/chat/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ business_slug_or_token: businessSlug, channel: 'widget' })
    })
      .then(r => r.json())
      .then(d => { sessionId = d.id; })
      .catch(e => console.error('[Iveri Widget] Session init failed:', e));
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
  function sendMessage(text) {
    if (!text || (typeof text === 'string' && !text.trim())) return;
    const msgText = text.trim();
    const msgsContainer = document.getElementById('iveri-msgs');

    // Append User Message
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
            badge.title = c.excerpt;
            badge.onclick = () => alert(`Source: ${c.document_name} (Page ${c.page_number})\n\nExcerpt:\n${c.excerpt}`);
            citeRow.appendChild(badge);
          });
          botBubble.appendChild(citeRow);
        }

        // Thumbs Up / Down
        const feedbackRow = document.createElement('div');
        feedbackRow.className = 'iveri-feedback-row';
        feedbackRow.innerHTML = `
          <button class="iveri-feedback-btn" title="Helpful">👍</button>
          <button class="iveri-feedback-btn" title="Not helpful">👎</button>
          <span style="font-size:10.5px; font-family:'JetBrains Mono',monospace; color:#94A3B8; margin-left:auto;">${data.latency_ms}ms</span>
        `;
        const buttons = feedbackRow.querySelectorAll('button');
        buttons[0].onclick = () => sendFeedback(data.id, 'up', feedbackRow);
        buttons[1].onclick = () => sendFeedback(data.id, 'down', feedbackRow);
        botBubble.appendChild(feedbackRow);

        // Lead capture if unknown
        if (!data.is_answered) {
          const leadBox = document.createElement('div');
          leadBox.style.marginTop = '8px';
          leadBox.style.padding = '8px 10px';
          leadBox.style.background = '#FFFBEB';
          leadBox.style.border = '1px solid #FDE68A';
          leadBox.style.borderRadius = '8px';
          leadBox.innerHTML = `
            <div style="font-size:11.5px; color:#92400E; font-weight:500; margin-bottom:4px;">Need team follow-up?</div>
            <div style="display:flex; gap:6px;">
              <input type="email" placeholder="your@email.com" style="flex:1; padding:4px 8px; font-size:11.5px; background:#FFFFFF; color:#0F172A; border:1px solid #CBD5E1; border-radius:4px;" />
              <button style="padding:4px 8px; font-size:11.5px; background:#D97706; color:white; border:none; border-radius:4px; font-weight:600; cursor:pointer;">Send</button>
            </div>
          `;
          const btn = leadBox.querySelector('button');
          const inp = leadBox.querySelector('input');
          btn.onclick = () => {
            if (inp.value) {
              fetch(`${apiBaseUrl}/api/chat/session/${sessionId}/lead`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: inp.value })
              }).then(() => { leadBox.innerHTML = '<span style="font-size:11.5px; color:#059669; font-weight:500;">✓ Email recorded! Team will reach out.</span>'; });
            }
          };
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
})();