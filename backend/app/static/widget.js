(function () {
  // Find script element and extract configuration
  const currentScript = document.currentScript || (function() {
    const scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  })();

  const businessSlug = currentScript.getAttribute('data-business') || '';
  const apiBaseUrl = currentScript.getAttribute('data-api') || window.location.origin;

  if (!businessSlug) {
    console.error('[Iveri Widget] Missing data-business attribute.');
    return;
  }

  let sessionId = null;
  let businessData = {
    name: 'Customer Support',
    brand_color: '#2563eb',
    starter_questions: ['What are your hours?', 'What is your refund policy?']
  };

  // Inject CSS Styles
  const style = document.createElement('style');
  style.innerHTML = `
    .iveri-widget-bubble {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      box-shadow: 0 4px 14px rgba(0,0,0,0.2);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 999999;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
      background-color: #2563eb;
      color: white;
    }
    .iveri-widget-bubble:hover {
      transform: scale(1.06);
      box-shadow: 0 6px 20px rgba(0,0,0,0.25);
    }
    .iveri-widget-window {
      position: fixed;
      bottom: 96px;
      right: 24px;
      width: 380px;
      height: 580px;
      max-width: calc(100vw - 32px);
      max-height: calc(100vh - 120px);
      background: white;
      border-radius: 16px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.18);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 999999;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .iveri-widget-header {
      padding: 16px 20px;
      color: white;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .iveri-widget-messages {
      flex: 1;
      padding: 16px;
      overflow-y: auto;
      background: #f8fafc;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .iveri-msg {
      max-width: 82%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 14px;
      line-height: 1.45;
      word-break: break-word;
    }
    .iveri-msg-user {
      align-self: flex-end;
      background: #2563eb;
      color: white;
      border-bottom-right-radius: 4px;
    }
    .iveri-msg-assistant {
      align-self: flex-start;
      background: white;
      color: #1e293b;
      border: 1px solid #e2e8f0;
      border-bottom-left-radius: 4px;
    }
    .iveri-citation-badge {
      display: inline-block;
      margin-top: 6px;
      padding: 3px 8px;
      background: #eff6ff;
      color: #1d4ed8;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 500;
      border: 1px solid #bfdbfe;
      cursor: pointer;
    }
    .iveri-feedback-row {
      display: flex;
      gap: 6px;
      margin-top: 6px;
    }
    .iveri-feedback-btn {
      background: none;
      border: none;
      cursor: pointer;
      font-size: 12px;
      padding: 2px 4px;
      opacity: 0.6;
      transition: opacity 0.2s;
    }
    .iveri-feedback-btn:hover {
      opacity: 1;
    }
    .iveri-starters {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }
    .iveri-starter-pill {
      background: white;
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      padding: 6px 12px;
      font-size: 12px;
      color: #334155;
      cursor: pointer;
      transition: background 0.15s;
    }
    .iveri-starter-pill:hover {
      background: #f1f5f9;
    }
    .iveri-input-box {
      padding: 12px 16px;
      background: white;
      border-top: 1px solid #e2e8f0;
      display: flex;
      gap: 8px;
    }
    .iveri-input {
      flex: 1;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 14px;
      outline: none;
    }
    .iveri-input:focus {
      border-color: #2563eb;
    }
    .iveri-send-btn {
      background: #2563eb;
      color: white;
      border: none;
      border-radius: 8px;
      padding: 8px 14px;
      cursor: pointer;
      font-weight: 500;
    }
  `;
  document.head.appendChild(style);

  // Create Widget DOM
  const bubble = document.createElement('div');
  bubble.className = 'iveri-widget-bubble';
  bubble.innerHTML = `
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
    </svg>
  `;

  const chatWindow = document.createElement('div');
  chatWindow.className = 'iveri-widget-window';
  chatWindow.innerHTML = `
    <div class="iveri-widget-header" id="iveri-header">
      <div>
        <div style="font-weight: 600; font-size: 15px;" id="iveri-biz-name">Support Assistant</div>
        <div style="font-size: 11px; opacity: 0.85;">● Online 24/7</div>
      </div>
      <button style="background:none; border:none; color:white; font-size:20px; cursor:pointer;" id="iveri-close">×</button>
    </div>
    <div class="iveri-widget-messages" id="iveri-msgs">
      <div class="iveri-msg iveri-msg-assistant">
        Hello! How can I assist you today?
        <div class="iveri-starters" id="iveri-starter-container"></div>
      </div>
    </div>
    <div class="iveri-input-box">
      <input type="text" class="iveri-input" id="iveri-input" placeholder="Type your question..." />
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
      bubble.style.backgroundColor = data.brand_color || '#2563eb';
      document.getElementById('iveri-header').style.backgroundColor = data.brand_color || '#2563eb';
      document.getElementById('iveri-send').style.backgroundColor = data.brand_color || '#2563eb';
      document.getElementById('iveri-biz-name').innerText = data.name || 'Support Assistant';
      
      const starterContainer = document.getElementById('iveri-starter-container');
      starterContainer.innerHTML = '';
      (data.starter_questions || []).forEach(q => {
        const pill = document.createElement('button');
        pill.className = 'iveri-starter-pill';
        pill.innerText = q;
        pill.onclick = () => sendMessage(q);
        starterContainer.appendChild(pill);
      });
    })
    .catch(err => console.warn('[Iveri Widget] Failed to load business branding:', err));

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

  // Send Message
  function sendMessage(text) {
    if (!text || !text.strip ? !text.trim() : !text) return;
    const msgText = text.trim();
    const msgsContainer = document.getElementById('iveri-msgs');

    // Append User Message
    const userBubble = document.createElement('div');
    userBubble.className = 'iveri-msg iveri-msg-user';
    userBubble.style.backgroundColor = businessData.brand_color || '#2563eb';
    userBubble.innerText = msgText;
    msgsContainer.appendChild(userBubble);
    msgsContainer.scrollTop = msgsContainer.scrollHeight;

    // Append Assistant Loading Indicator
    const botBubble = document.createElement('div');
    botBubble.className = 'iveri-msg iveri-msg-assistant';
    botBubble.innerText = 'Thinking...';
    msgsContainer.appendChild(botBubble);
    msgsContainer.scrollTop = msgsContainer.scrollHeight;

    fetch(`${apiBaseUrl}/api/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: msgText })
    })
      .then(r => r.json())
      .then(data => {
        botBubble.innerHTML = `<div>${data.content}</div>`;

        // Citations
        if (data.citations && data.citations.length > 0) {
          const citeRow = document.createElement('div');
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
        `;
        const buttons = feedbackRow.querySelectorAll('button');
        buttons[0].onclick = () => sendFeedback(data.id, 'up', feedbackRow);
        buttons[1].onclick = () => sendFeedback(data.id, 'down', feedbackRow);
        botBubble.appendChild(feedbackRow);

        // Lead capture if unknown
        if (!data.is_answered) {
          const leadBox = document.createElement('div');
          leadBox.style.marginTop = '8px';
          leadBox.innerHTML = `
            <div style="font-size:12px; color:#64748b; margin-bottom:4px;">Want our team to email you?</div>
            <input type="email" placeholder="your@email.com" style="width:70%; padding:4px 6px; font-size:12px; border:1px solid #cbd5e1; border-radius:4px;" />
            <button style="padding:4px 8px; font-size:12px; background:#2563eb; color:white; border:none; border-radius:4px; cursor:pointer;">Submit</button>
          `;
          const btn = leadBox.querySelector('button');
          const inp = leadBox.querySelector('input');
          btn.onclick = () => {
            if (inp.value) {
              fetch(`${apiBaseUrl}/api/chat/session/${sessionId}/lead`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: inp.value })
              }).then(() => { leadBox.innerHTML = '<span style="font-size:12px; color:#10b981;">✓ Email received! We will follow up.</span>'; });
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
      rowEl.innerHTML = `<span style="font-size:11px; color:#64748b;">Thanks for your feedback (${vote === 'up' ? '👍' : '👎'})!</span>`;
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
