# Iveri — Autonomous AI Customer Support Assistant
## Automated Ticketing, Closed-Loop Learning, Twilio WhatsApp Gateway & Mobile PWA Architecture

---

### 1. Executive Summary

Iveri has evolved from an informational retrieval chatbot into a **full-fledged autonomous AI customer service assistant**. 

This document details the architectural expansion delivering:
1. **Automated Fallback & Urgent Contact Ticketing**: When the AI encounters an unanswerable question or when a visitor requests human contact, an official support ticket (`TICK-XXXX`) is automatically generated and an email alert is dispatched to the business owner.
2. **Closed-Loop Knowledge Base Self-Improvement**: Business owners can resolve tickets in 1-click via the dashboard. Resolving a ticket permanently indexes the verified Question & Answer into ChromaDB and BM25, ensuring the AI assistant learns it immediately and never fails that query again.
3. **Public WhatsApp Interface via Twilio**: Customers can interact with the store's AI directly over WhatsApp using Twilio's webhook infrastructure and TwiML XML. WhatsApp conversations seamlessly sync with the owner's dashboard in real-time.
4. **Multi-Channel In-App & Mobile Push Notifications**: Instant notification bell with unread counters, in-app alert drawer, and standard VAPID Web Push notifications for urgent tickets and customer callbacks.
5. **Mobile Progressive Web App (PWA) & Custom Branding**: High-resolution bespoke Iveri AI avatar/DP, `manifest.json`, and service worker (`sw.js`) enabling homescreen installation on iOS and Android with offline asset caching.

---

### 2. Automated Support Ticketing System

#### 2.1 Workflow & Trigger Mechanics
The ticketing engine operates on two complementary channels:

```
                  +-----------------------------------------+
                  |         Customer Conversation           |
                  |     (Web Widget / Twilio WhatsApp)      |
                  +-----------------------------------------+
                                       |
                 +---------------------+---------------------+
                 |                                           |
                 v                                           v
    [AI Query / RAG Pipeline]                  [Explicit Human Contact Request]
                 |                                           |
                 v                                           v
       Is Question Answered?                       POST /api/chat/contact-request
    (Confidence >= 0.55 & Chunks)                            |
                 |                                           v
        +--------+--------+                         Create Urgent Ticket
        |                 |                        (Priority: "urgent")
       YES                NO                                 |
        |                 |                                  |
        v                 v                                  |
    Respond with    Auto-Create Ticket                       |
     Confidence     (Priority: "medium")                     |
                          |                                  |
                          +-----------------+----------------+
                                            |
                                            v
                         +--------------------------------------+
                         |    Notification & Dispatch Loop      |
                         |  1. DB Record: TICK-XXXX             |
                         |  2. In-App Notification (Unread Bell)|
                         |  3. Owner HTML Email Alert           |
                         |  4. Mobile Web Push (VAPID)          |
                         +--------------------------------------+
```

#### 2.2 Database Schema (`tickets` table)
- `id`: UUID Primary Key.
- `ticket_number`: Human-readable identifier (`TICK-XXXX` format, unique indexed).
- `business_id`: Multi-tenant isolation foreign key.
- `session_id` & `message_id`: Linked conversation thread.
- `customer_name`, `customer_email`, `customer_phone`: Captured customer identity.
- `channel`: Originating touchpoint (`widget`, `whatsapp`, `public_link`).
- `priority`: `urgent`, `high`, `medium`, `low`.
- `status`: `open`, `in_progress`, `resolved`.
- `resolved_answer`: Owner's verified resolution text.
- `resolved_at`: Timestamp of resolution.

#### 2.3 Closed-Loop Learning
When the business owner resolves a ticket via `POST /api/tickets/{id}/resolve`:
1. The ticket status updates to `resolved` with the owner's provided answer.
2. A new `Document` with `file_type="manual_qa"` and corresponding `DocumentChunk` are generated.
3. The Question and Verified Answer pair is immediately embedded and indexed into **ChromaDB** (Dense Vector) and **BM25** (Sparse Lexical).
4. Subsequent customer queries immediately retrieve the newly learned answer with high confidence.

---

### 3. Twilio WhatsApp Business Gateway

#### 3.1 Why Twilio
- **Instant Sandbox Activation**: Zero waiting period or Meta Business Verification hurdles for testing. Simply text `join <sandbox-code>` to `+1 415 523 8886`.
- **TwiML XML Execution**: Instant, synchronous `<Response><Message>...</Message></Response>` delivery without requiring outbound token handshakes or external state workers.
- **Dual Content-Type Support**: Seamlessly accepts both standard `application/x-www-form-urlencoded` (Twilio webhook default) and `application/json`.

#### 3.2 Webhook Flow (`POST /api/chat/twilio/{slug}/webhook`)
1. **Phone Identity**: Normalizes customer phone number from Twilio's `From=whatsapp:+1234567890` format.
2. **Session Persistence**: Reuses existing WhatsApp session or creates a new one tagged with `channel="whatsapp"`.
3. **RAG & Safeguards**: Executes the full 5-stage pipeline (OWASP sanitize, Laya intent classification, hybrid retrieval, circuit breaker, cascading LLM).
4. **Fallback & Ticket Creation**: If the AI cannot answer, creates a ticket tagged with `channel="whatsapp"` and informs the customer that store management has been notified.
5. **Dashboard Visibility**: Transcripts appear in real-time under the **Chat History (2-Pane)** tab with a dedicated WhatsApp channel badge.

---

### 4. Real-Time In-App & Mobile Push Notifications

#### 4.1 Generous & Free Tooling
- **In-App Notification Center**: Built directly into SQLite/PostgreSQL (`notifications` table). Zero external cost or third-party dependencies.
- **Web Push Notifications (VAPID RFC 8292)**: Uses native browser Web Push API (supported across Chrome, Edge, Firefox, and iOS Safari 16.4+). 100% free with unlimited notifications and persistent 24-hour delivery TTL.
- **Background Delivery (App Closed)**: Push events wake the browser's Service Worker even when the PWA is closed or running in the background. Incoming notifications trigger native OS notification banners and update app badges immediately.
- **Native OS App Badging & Header DP Counter**:
  - The Service Worker executes `navigator.setAppBadge(count)` in `event.waitUntil()`, displaying an unread counter badge directly on the home screen PWA icon (like WhatsApp).
  - Inside the web app, the user's header avatar DP features a real-time glowing unread badge pill (`#avatar-unread-badge`) synchronized via push state and database query.
- **Owner Email Dispatch**: Supports free tiers of SMTP (Gmail/Brevo) and Resend (`resend_api_key`), with automated local mock fallback when credentials are not configured.

#### 4.2 Notification Payload & Actions
- **New Support Ticket**: Category `auto_ticket` | Priority `medium` | One-click jump to ticket resolution.
- **Urgent Callback Request**: Category `urgent_contact` | Priority `urgent` | Displays customer contact phone number.
- **WhatsApp Inbound**: Category `whatsapp` | Priority `medium` | Links to WhatsApp conversation thread.

---

### 5. Progressive Web App (PWA) & Custom DP

#### 5.1 Bespoke App Icons & DP
- **Master Avatar**: `backend/app/static/icons/iveri-avatar.svg` — high-fidelity geometric robot avatar with indigo-to-purple gradient, glowing neural eyes, and store headset.
- **App Icons**: 192x192, 512x512, Apple Touch Icon, and favicon generated with crisp anti-aliased rendering.
- **Theme Color**: Indigo (`#4F46E5`), styled for Android navigation bars and iOS Safari status bar translucent headers.

#### 5.2 Manifest, Service Worker & Sub-50ms Installation
- `backend/app/static/manifest.json`: Defines standalone display mode, orientation, name, icons, and explicitly configures `"prefer_related_applications": false` to prioritize immediate WebAPK compilation.
- `backend/app/static/sw.js`:
  - **Ultra-Fast Non-Blocking Install**: The `install` lifecycle pre-caches only the minimal critical shell (`manifest.json` and essential app icons) in under 50ms, eliminating Android Chrome WebAPK server timeout stalls.
  - **Dynamic Runtime Caching**: All auxiliary assets, stylesheets, and fonts are fetched on-demand with stale-while-revalidate caching.
  - **Background Push & Badging**: Listens to native `push` events, invokes `self.registration.showNotification()`, and asynchronously dispatches `navigator.setAppBadge()` to illuminate the home screen app icon.

---

### 6. Zero-Trust Access Control & Tab Gating

To protect proprietary business knowledge and customer communication transcripts:
- **Public Overview Access**: Unauthenticated visitors can view the platform Overview tab, which displays public features, metrics summary, and the sign-in / registration trigger.
- **Strict Tab Gating**: Protected tabs (**Documents**, **Unanswered / Tickets**, **Customer Chats**, and **Settings & Studio**) require an authenticated session token.
- **Automated Sign-In Prompt**: Any unauthorized attempt to click a protected tab immediately cancels navigation, displays an informative security notice, and triggers the modular authentication modal (`openAuthModal()`).
- **Cryptographic Export Isolation**: Telemetry datasets (`/api/dashboard/export/powerbi`) require active JWT authentication and are strictly isolated to the authenticated business ID, eliminating unauthenticated data scraping.

---

### 7. API Route Reference

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/tickets` | List tickets with status, priority, channel, and search filters | Owner JWT |
| `GET` | `/api/tickets/{id}` | Retrieve individual ticket details | Owner JWT |
| `POST` | `/api/tickets/{id}/resolve` | Resolve ticket & auto-index Q&A into ChromaDB & BM25 | Owner JWT |
| `DELETE` | `/api/tickets/{id}` | Permanently delete ticket and clean up orphaned notifications | Owner JWT |
| `POST` | `/api/chat/contact-request` | Public customer contact/callback request submission | Public |
| `GET` | `/api/notifications` | List owner notifications with unread count | Owner JWT |
| `POST` | `/api/notifications/{id}/read` | Mark individual notification as read | Owner JWT |
| `POST` | `/api/notifications/read-all` | Mark all notifications as read | Owner JWT |
| `GET` | `/api/notifications/push/public-key` | Retrieve VAPID public key for browser push subscription | Public |
| `POST` | `/api/notifications/push/subscribe` | Register browser push subscription token | Owner JWT |
| `GET` | `/api/notifications/push/status` | Audit registered push subscriptions for active tenant | Owner JWT |
| `GET` | `/api/dashboard/export/powerbi` | Export live telemetry dataset (CSV/JSON) strictly scoped to business | Owner JWT (Bearer or `?token=`) |
| `POST` | `/api/chat/twilio/{slug}/webhook` | Twilio WhatsApp incoming webhook handler | Twilio Signature / Public |
| `GET` | `/api/chat/twilio/{slug}/config` | Retrieve Twilio webhook endpoint and sandbox setup guide | Owner JWT |

---

### 8. Automated Test Suite & CI/CD Verification

All features are covered by automated unit and evaluation test suites passing 100%:

```bash
# 1. Safety Guardrails & Adversarial Evals (8 tests)
python -m unittest backend/tests/test_guardrails_evals.py

# 2. Authentication & Business Management (6 tests)
python -m unittest backend/tests/test_phase1_phase2.py

# 3. Hybrid RAG & Pre-LLM Circuit Breaker (6 tests)
python -m unittest backend/tests/test_phase3_rag.py

# 4. Chat Endpoints & Widget Serving (5 tests)
python -m unittest backend/tests/test_phase4_chat.py

# 5. Dashboard Analytics & 2-Pane Conversation Audit (5 tests)
python -m unittest backend/tests/test_phase5_dashboard.py

# 6. Support Tickets, Notifications & Twilio WhatsApp (8 tests)
python -m unittest backend/tests/test_tickets_notifications_twilio.py

# 7. Zero-Trust Tab Gating & UI Access Contracts (3 tests)
python -m unittest backend/tests/test_ui_tab_contracts.py

# 8. Web Push Badging & UI Notification Lifecycle (14 tests)
python -m unittest backend/tests/test_notifications_and_ui_enhancements.py

# 9. Power BI Strict Authenticated Export & Phase 6 Features (5 tests)
python -m unittest backend/tests/test_phase6_features.py
```

**Total Verification Suite**: **50+ comprehensive unit, integration, and security tests executed and passing.**
