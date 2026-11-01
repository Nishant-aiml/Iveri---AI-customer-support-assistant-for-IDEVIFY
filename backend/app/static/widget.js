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
    brand_color: '#6366F1',
    starter_questions: []
  };

  // Inject Obsidian Kinetic CSS Styles
  const style = document.createElement('style');
  style.innerHTML = `
    @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
    
    .iveri-widget-bubble {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 58px;
      height: 58px;
      border-radius: 50%;
      box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4), inset 0 1px 0 rgba(255,255,255,0.2);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 999999;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
      background-color: #6366F1;
      color: white;
    }
    .iveri-widget-bubble:hover {
      transform: scale(1.08);
      box-shadow: 0 8px 25px rgba(99, 102, 241, 0.55);
    }
    .iveri-widget-window {
      position: fixed;
      bottom: 96px;
      right: 24px;
      width: 380px;
      height: 580px;
      max-width: calc(100vw - 32px);
      max-height: calc(100vh - 120px);
      background: #131622;
      border: 1px solid #1F2438;
      border-radius: 18px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.06);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 999999;
      font-family: 'Geist', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #E2E1ED;
    }
    .iveri-widget-header {
      padding: 14px 18px;
      background: #0D0F17;
      border-bottom: 1px solid #1F2438;
      color: white;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .iveri-widget-messages {
      flex: 1;
      padding: 16px;
      overflow-y: auto;
      background: #090A0F;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .iveri-msg {
      max-width: 84%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 13.5px;
      line-height: 1.45;
      word-break: break-word;
    }
    .iveri-msg-user {
      align-self: flex-end;
      background: #1A1E2E;
      color: #F8FAFC;
      border: 1px solid #2B334E;
      border-bottom-right-radius: 4px;
    }
    .iveri-msg-assistant {
      align-self: flex-start;
      background: #131622;
      color: #E2E1ED;
      border: 1px solid #1F2438;
      border-bottom-left-radius: 4px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
    }
    .iveri-citation-badge {
      display: inline-block;
      margin-top: 6px;
      padding: 3px 8px;
      background: rgba(16, 185, 129, 0.1);
      color: #10B981;
      border-radius: 6px;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 500;
      border: 1px solid rgba(16, 185, 129, 0.25);
      cursor: pointer;
      transition: background 0.15s;
    }
    .iveri-citation-badge:hover {
      background: rgba(16, 185, 129, 0.2);
    }
    .iveri-feedback-row {
      display: flex;
      gap: 6px;
      margin-top: 6px;
      align-items: center;
    }
    .iveri-feedback-btn {
      background: #0D0F17;
      border: 1px solid #1F2438;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
      padding: 3px 6px;
      color: #94A3B8;
      transition: all 0.15s;
    }
    .iveri-feedback-btn:hover {
      color: #E2E1ED;
      border-color: #6366F1;
    }
    .iveri-starters {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }
    .iveri-starter-pill {
      background: #0D0F17;
      border: 1px solid #1F2438;
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 12px;
      color: #94A3B8;
      cursor: pointer;
      transition: all 0.15s;
    }
    .iveri-starter-pill:hover {
      background: #1A1E2E;
      border-color: #6366F1;
      color: white;
    }
    .iveri-input-box {
      padding: 12px 14px;
      background: #0D0F17;
      border-top: 1px solid #1F2438;
      display: flex;
      gap: 8px;
    }
    .iveri-input {
      flex: 1;
      background: #090A0F;
      color: white;
      border: 1px solid #1F2438;
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13.5px;
      outline: none;
      transition: border 0.15s;
    }
    .iveri-input:focus {
      border-color: #6366F1;
    }
    .iveri-send-btn {
      background: #6366F1;
      color: white;
      border: none;
      border-radius: 8px;
      padding: 8px 14px;
      cursor: pointer;
      font-weight: 500;
      font-size: 13px;
      transition: background 0.15s;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.2);
    }
    .iveri-send-btn:hover {
      background: #4F46E5;
    }
  `;
  document.head.appendChild(style);

  // Create Widget DOM
  const bubble = document.createElement('div');
  bubble.className = 'iveri-widget-bubble';
  bubble.innerHTML = `
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
    </svg>
  `;

  const chatWindow = document.createElement('div');
  chatWindow.className = 'iveri-widget-window';
  chatWindow.innerHTML = `
    <div class="iveri-widget-header" id="iveri-header">
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#10B981;"></span>
        <div>
          <div style="font-weight: 600; font-size: 14px;" id="iveri-biz-name">Support Assistant</div>
          <div style="font-size: 10px; font-family:'JetBrains Mono', monospace; opacity: 0.75;">Grounded RAG • Online</div>
        </div>
      </div>
      <button style="background:none; border:none; color:#94A3B8; font-size:20px; cursor:pointer;" id="iveri-close">×</button>
    </div>
    <div class="iveri-widget-messages" id="iveri-msgs">
      <div class="iveri-msg iveri-msg-assistant">
        Hello! How can I assist you today?
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
      if (data.brand_color && data.brand_color !== '#2563eb') {
        bubble.style.backgroundColor = data.brand_color;
        document.getElementById('iveri-send').style.backgroundColor = data.brand_color;
      }
      document.getElementById('iveri-biz-name').innerText = data.name || 'Support Assistant';
      
      const starterContainer = document.getElementById('iveri-starter-container');
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
          <span style="font-size:10px; font-family:'JetBrains Mono',monospace; color:#64748B; margin-left:auto;">${data.latency_ms}ms</span>
        `;
        const buttons = feedbackRow.querySelectorAll('button');
        buttons[0].onclick = () => sendFeedback(data.id, 'up', feedbackRow);
        buttons[1].onclick = () => sendFeedback(data.id, 'down', feedbackRow);
        botBubble.appendChild(feedbackRow);

        // Lead capture if unknown
        if (!data.is_answered) {
          const leadBox = document.createElement('div');
          leadBox.style.marginTop = '8px';
          leadBox.style.padding = '8px';
          leadBox.style.background = '#1A1811';
          leadBox.style.border = '1px solid rgba(245,158,11,0.3)';
          leadBox.style.borderRadius = '8px';
          leadBox.innerHTML = `
            <div style="font-size:11.5px; color:#FBBF24; margin-bottom:4px;">Need team follow-up?</div>
            <div style="display:flex; gap:6px;">
              <input type="email" placeholder="your@email.com" style="flex:1; padding:4px 8px; font-size:11.5px; background:#090A0F; color:white; border:1px solid #1F2438; border-radius:4px;" />
              <button style="padding:4px 8px; font-size:11.5px; background:#D97706; color:white; border:none; border-radius:4px; cursor:pointer;">Send</button>
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
              }).then(() => { leadBox.innerHTML = '<span style="font-size:11.5px; color:#10B981;">✓ Email recorded! Team will reach out.</span>'; });
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
      rowEl.innerHTML = `<span style="font-size:11px; font-family:'JetBrains Mono',monospace; color:${vote==='up'?'#10B981':'#F43F5E'};">Feedback recorded (${vote === 'up' ? '✓' : '✕'})</span>`;
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
