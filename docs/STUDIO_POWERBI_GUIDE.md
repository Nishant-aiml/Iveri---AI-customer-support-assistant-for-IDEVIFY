# Widget Studio & Power BI Integration Guide

This guide details the operational architecture, setup procedures, and security controls for Iveri's Widget Studio, Power BI live analytics pipeline, and customer sentiment telemetry.

---

## 1. Power BI & Excel Live Dataset Integration

### Architecture & Authentication
Iveri provides high-speed, flattened tabular export designed specifically for Power BI, Excel Power Query, and Tableau dashboards.

- **Endpoint**: `/api/dashboard/export/powerbi`
- **Supported Formats**: `csv` (default), `json`
- **Zero-Trust Multi-Tenant Security**:
  1. **Strict Authentication Enforced**: All requests to this endpoint strictly require a valid, non-expired JWT authentication token. Unauthenticated requests strictly receive `401 Unauthorized` (no anonymous or unauthenticated fallback).
  2. **Multi-Tenant Data Scoping**: Datasets are strictly isolated by `business_id` derived directly from the verified cryptographic JWT payload. Business owners can only access conversation telemetry for their own registered store.
- **Authentication Methods**:
  1. **Authorization Header**: `Bearer <JWT_TOKEN>` (for programmatic SDK callers).
  2. **URL Query Parameter**: `?token=<JWT_TOKEN>` (for Power BI Desktop Web Connector, Excel Web Queries, and automated scheduled refreshes).
- **Frontend Dashboard Controls**:
  - The **Download CSV** and **Power BI URL** buttons in the Executive Telemetry header are strictly gated behind authentication.
  - If an unauthenticated visitor attempts to click either action, the system automatically interrupts execution, issues a security guidance notice, and opens the **Sign In** authentication modal.
  - When authenticated, "Download CSV" performs a secure blob download using the active session token, and "Power BI URL" copies the token-parameterized link to the clipboard.

### Connecting Power BI Desktop to Live Iveri Telemetry
1. Open **Power BI Desktop**.
2. Click **Get Data** $\rightarrow$ **Web**.
3. In the URL dialog, paste your live Web Connector URL (copied with 1 click from the Executive Intelligence Dashboard):
   ```
   http://localhost:8000/api/dashboard/export/powerbi?format=csv&token=<YOUR_TOKEN>
   ```
4. Select **Anonymous** authentication (the security token is embedded securely in the query parameter).
5. Click **Connect** and **Load**. Your live dashboard now has access to:
   - `SessionID`, `Timestamp`, `CustomerEmail`, `Channel`, `Sender`
   - `MessageContent`, `IsAnswered`, `Topic`, `Sentiment`, `Feedback`
   - `LatencyMS`, `LLMProvider`, `CitationsCount`, `ConfidenceScore`

---

## 2. Widget Studio & Chatbot Customization

### Local Device Avatar DP Upload
Business owners can upload a custom chatbot avatar directly from their local machine:
- **Endpoint**: `POST /api/business/avatar/upload`
- **Supported Formats**: `PNG`, `JPEG`, `WEBP`, `SVG` (enforced via magic number inspection and content-type validation).
- **Max File Size**: 5 MB.
- **Serving Path**: `/api/business/avatar/{filename}` with long-lived client caching headers (`Cache-Control: public, max-age=86400`).

### Dedicated Chatbot Custom Prompt & Persona Guidance
Store owners can tailor the personality and domain hospitality of their assistant using the **Custom AI Prompt** field in Widget Studio:
- **System Prompt Priority Hierarchy**:
  1. **Grounding & Zero Hallucination (Highest Priority)**: The assistant must answer strictly from verified document excerpts. If a query cannot be answered from uploaded policies or catalogs, it must decline or offer lead capture.
  2. **Persona & Tone Instructions**: Hospitality guidelines (e.g., "You are a warm coffee sommelier for BrewNest Coffee Co.") format the delivery style without fabricating unverified information.

### Public Standalone Chatbot Link
Every registered store receives a universal permalink:
```
https://your-domain.com/chat/<business-slug>
```
The link can be copied with 1 click from Widget Studio and shared with customers, partners, or team members for standalone testing and support.

---

## 3. Executive Intelligence & Interactive Chart Drill-Down

### Multi-Message Sentiment Hierarchy
To prevent frustrated customers from being masked as neutral if they say "okay" or "bye" at the end of a session:
- A `ChatSession` is classified as **`negative`** if:
  - Any customer message was analyzed as negative by the VADER/lexicon sentiment engine, OR
  - Any message received a thumbs-down ($\text{👎}$) feedback rating.
- A session is classified as **`positive`** if any message is positive or received a thumbs-up ($\text{👍}$) without negative flags.

### Interactive Chart Drill-Down
Clicking on any segment of the dashboard charts dynamically filters the 2-Pane Chat History:
- **Customer Sentiment Chart**: Clicking **Frustrated/Negative** immediately switches to the Chat History tab with `sentiment=negative` filtered.
- **Top Inquiry Topics Chart**: Clicking any topic bar (e.g., `PRICING`, `RETURNS`) automatically filters chat sessions by that topic.
