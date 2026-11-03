# Product Requirements Document (PRD)
## Project: AI Customer Support Assistant (Multi-Tenant RAG Platform)

---

| Document Metadata | Specification |
| :--- | :--- |
| **Product Name** | AI Customer Support Assistant (Iveri) |
| **Document Version** | 1.2.0 (Enterprise Asset & Multi-Tenant Specification) |
| **Status** | Approved & Production Baselined |
| **Primary Code Repository** | [https://github.com/Nishant-aiml/Iveri---AI-customer-support-assistant-for-IDEVIFY.git](https://github.com/Nishant-aiml/Iveri---AI-customer-support-assistant-for-IDEVIFY.git) |
| **Secondary / Mirror Repo** | [https://github.com/ishwaribhoyar/Iveri-AI-customer-support-assistant-for-IDEVIFY.git](https://github.com/ishwaribhoyar/Iveri-AI-customer-support-assistant-for-IDEVIFY.git) |
| **Target Platforms** | Web Application (Responsive Desktop & Mobile PWA) & Embeddable JS Widget |
| **Backend Stack** | Python 3.11+, FastAPI, SQLAlchemy (Async), ChromaDB, `rank-bm25`, `laya` |
| **Frontend Stack** | High-Density HTML5/Tailwind Glassmorphic Console, Vanilla JS Widget |
| **Database** | SQLite (Development) $\rightarrow$ PostgreSQL (Render Production) |

---

## 1. Product Vision & Strategic Architectural Philosophy

### 1.1 The Original Problem Statement (IDEVIFY Solutions Candidate Brief)
The evaluation assignment issued by **IDEVIFY Solutions Private Limited** defines the baseline problem:

> *"Small businesses get the same customer questions again and again (pricing, refund policy, delivery time), and a human has to answer each one. Generic chatbots give wrong answers because they know nothing about the business. Build a platform where a business uploads its own documents and gets an AI assistant that answers customer questions only from those documents."*
>
> **Core Deliverables Required**:
> 1. **Dual Roles**: Business Owner (Upload documents, view chat history, configure assistant) and Customer (Access public chat via unique link or embedded widget, ask questions, receive answers grounded strictly in uploaded documents with exact citations).
> 2. **Document Processing**: Intelligent ingestion supporting PDFs, DOCX, TXT, Excel/Spreadsheets, and OCR images with chunking, overlap, and vector indexing.
> 3. **Intelligent Grounded RAG**: Dense vector + sparse keyword search, polite fallbacks when information is absent, zero hallucination.
> 4. **Handling Unknowns & Fallbacks**: Friendly fallback responses when queries cannot be answered, with contact/callback logging.
> 5. **Dynamic Document Updates**: Immediate reflection of uploaded, edited, or deleted files in assistant knowledge base without stale answers.
> 6. **Production Polish**: Clean UX, robust multi-tenancy, and high evaluation scores across correctness and engineering design.

---

### 1.2 Strategic Transformation: From an Assignment into an IDEVIFY Enterprise Business Asset

While the original brief focused on a single chatbot-type service, our engineering team treated the prompt as a strategic challenge: **How do we build something that becomes a permanent commercial IP asset and recurring revenue engine for IDEVIFY Solutions Private Limited?**

IDEVIFY Solutions is an engineering consultancy serving multiple commercial clients. Nearly all clients need chatbot and customer support automation. Traditionally, agencies face a severe engineering bottleneck:
- **The Legacy Bottleneck (150–200 Hours per Client)**: An agency writes bespoke code for each client, hardcodes prompt templates, spins up separate VMs or GPU containers, and maintains disparate codebases.
- **The Iveri Multi-Tenant Paradigm (< 30 Seconds per Client)**: Instead of one-off custom bots, we built an entire multi-tenant AI ecosystem. When IDEVIFY signs a new client, an engineer or account executive simply:
  1. Creates an isolated tenant workspace in Iveri in **under 30 seconds**.
  2. Drops in the client's product catalog, manuals, warranty terms, and pricing tables.
  3. Copies the 1-line script embed tag (`<script src=".../widget.js" data-business="..."></script>`) and deploys it onto the client's website.
- **Commercial Impact for IDEVIFY**:
  - Converts one-time project delivery fees into high-margin recurring monthly subscription revenue (MRR).
  - Operates on a sub-120MB memory footprint, allowing dozens of concurrent business tenants to run inside a single cloud container with **95%+ gross margins**.
  - Acts as a reusable, proprietary software asset owned by IDEVIFY Solutions.

---

### 1.3 Core Product Vision
The **AI Customer Support Assistant (Iveri)** is a multi-tenant, retrieval-augmented generation (RAG) ecosystem that enables small businesses and enterprise clients to turn static documentation into an accurate, 24/7 AI customer support representative with verified citations and automated human handover.

### Core Architectural Pillars

```mermaid
flowchart TD
    Pillar1["1. Multi-Hybrid Advance RAG
• Dense Semantic (ChromaDB)
• Sparse Lexical (BM25)
• Reciprocal Rank Fusion (RRF)"]
    
    Pillar2["2. Less AI-Dependent Engineering
• Pre-LLM Confidence Circuit Breaker
• Deterministic Source Attribution
• Regex Greeting Interceptors
• Pure SQL Metrics Aggregation"]
    
    Pillar3["3. High-Fidelity Dual Ingestion
• Primary: Sarvam Document Intelligence API
• Fallback: PyMuPDF (fitz)
• Async Queue & Parallel Worker Pool"]
    
    Pillar4["4. Render 512MB RAM Compliance
• Gemini Flash (Primary Freemium API)
• Groq Llama 3.1 8B (Hosted Fallback)
• Zero-RAM In-Container LLM Overhead"]

    Pillar5["5. Continuous Learning Loop
• Resolve Unanswered Queries into Knowledge Base
• Answer Thumbs Up/Down Feedback
• Embeddable Widget Snippet"]

    Pillar1 --- Pillar2 --- Pillar3 --- Pillar4 --- Pillar5
```

---

## 2. High-Value Feature Matrix (Evaluation Boosters)

To maximize project quality and evaluation scoring while keeping execution strictly disciplined, features are tiered into execution waves:

| Feature | Category | Impact on Evaluation | Complexity | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Resolve Unanswered Qs into Knowledge Base** | **Wave 1 (Must Have)** | 🔥 **Highest** (Closes the RAG loop) | Low | Owner types an answer to an unanswered question; system saves it as a Q&A chunk into the vector & BM25 store. Next time asked, the AI answers it accurately! |
| **Answer Feedback (Thumbs Up / Down)** | **Wave 1 (Must Have)** | ⭐ High (Quality assurance signal) | Low | Users can vote on each answer. Votes saved to `chat_messages`. Owner can filter downvoted answers to spot weak documentation. |
| **Source Chunk Preview Modal** | **Wave 1 (Must Have)** | ⭐ High (Proves grounding) | Low | Clicking a citation badge opens a popover showing the exact extracted text chunk and page number from the file. |
| **Shareable Link + Embeddable Widget** | **Wave 1 (Must Have)** | ⭐ High (Production readiness) | Low-Med | Public `/chat/{business-slug}` page PLUS an embeddable `<script src=".../widget.js" data-business="..."></script>` snippet for third-party sites. |
| **Suggested Starter Questions** | **Wave 1 (Must Have)** | ⭐ High (User experience) | Low | 3–4 clickable question pills on chat open (e.g. "What is your refund policy?", "How long does shipping take?"). |
| **Streaming Answers (SSE)** | **Wave 2 (Medium Effort)** | Medium-High (Modern UX) | Med | Server-Sent Events stream tokens in real-time as generated by the LLM. |
| **Lead Capture / Human Handoff** | **Wave 2 (Medium Effort)** | Medium (Business value) | Low | When the assistant cannot answer, customers can leave their email. Owner sees this lead alongside the unanswered question. |
| **Owner Assistant Customization** | **Wave 2 (Medium Effort)** | Medium (Customizability) | Low | Owner can customize business name, tone (friendly vs formal), fallback message, and primary widget brand color. |
| **Test Playground** | **Wave 2 (Medium Effort)** | High (Demo tool) | Med | Internal chat panel where owner can test queries and see top-retrieved chunk scores and RRF ranks. |
| **Extended Dashboard Analytics** | **Wave 2 (Medium Effort)** | Medium (Operational insights) | Low-Med | Top asked questions, answer rate over time, latency tracking, most-cited documents. |

---

## 3. Capability Map & Module Decomposition

```mermaid
flowchart LR
    M1["1. auth-and-tenancy
(Tenants, Users, RBAC, Share Tokens, Settings)"] --> M2["2. ingestion-engine
(Queue, Sarvam API, PyMuPDF, Chunker, Manual Q&A)"]
    
    M2 --> M3["3. retrieval-engine
(Chroma Dense, BM25 Sparse, RRF)"]
    
    M3 --> M4["4. decision-gate-and-llm
(Circuit Breaker, Gemini/Groq, Citations)"]
    
    M4 --> M5["5. chat-service
(Sessions, Messages, Feedback, SSE Stream, Widget)"]
    
    M5 --> M6["6. owner-dashboard
(Analytics, Unanswered Q&A Resolver, History, Playground)"]
```

---

## 4. Detailed Functional Specifications

### 4.1 Module 1: `auth-and-tenancy`
- **FR-101**: User registration with roles: `owner` (creates a business workspace) and `customer`.
- **FR-102**: Password hashing using `bcrypt` / `passlib` and stateless JWT session generation.
- **FR-103**: Unique, non-guessable `share_token` (UUID v4) and customizable URL `slug` for every business.
- **FR-104**: Public endpoint `GET /api/public/tenant/:slugOrToken` resolving business name, starter questions, brand color, and tone.
- **FR-105**: Multi-tenant database middleware enforcing `WHERE business_id = current_tenant_id` on every query.
- **FR-106 (Settings)**: Owner can update business name, tone (`formal` | `friendly`), custom fallback message, and widget hex color.

### 4.2 Module 2: `ingestion-engine`
- **FR-201 (File Support)**: Supports `.pdf`, `.docx`, and `.txt` files up to 25MB per file.
- **FR-202 (Dual Extraction Pipeline)**:
  - *Primary*: Sarvam Document Intelligence API (`https://api.sarvam.ai`) using `SARVAM_API_KEY`. Captures tables, multi-column layouts, and multilingual Indic/English text into clean Markdown.
  - *Fallback*: Local `PyMuPDF` (`fitz`) for PDF, `python-docx` for DOCX, and native UTF-8 for TXT.
- **FR-203 (Queue-Based Processing)**:
  - Upload endpoint `POST /api/documents/upload` returns `HTTP 202 Accepted` (`{document_id, status: "QUEUED"}`).
  - Async worker pool (`ThreadPoolExecutor` + `asyncio.Queue`) executes extraction and chunking in the background.
- **FR-204 (Recursive Chunking)**:
  - Chunks text into ~500–800 character windows with 10% overlap.
  - Enriches each chunk with metadata: `{business_id, document_id, document_name, chunk_index, page_number}`.
- **FR-205 (Manual Q&A Resolution Ingestion)** ⭐:
  - Endpoint `POST /api/documents/manual-qa` allows saving an answered question as a persistent knowledge document (`doc_type: "manual_qa"`).
  - Immediately generates embeddings and BM25 tokens, injecting the verified Q&A into the retrieval index!
- **FR-206 (Document CRUD)**:
  - Document listing with status (`QUEUED`, `PROCESSING`, `INDEXED`, `FAILED`).
  - Document deletion instantly purges all associated chunks from ChromaDB and BM25 index.

### 4.3 Module 3: `retrieval-engine`
- **FR-301 (Dense Vector Retrieval)**:
  - Embeds chunks using Google Gemini `text-embedding-004` (or Voyage AI / OpenAI).
  - ChromaDB index filtered strictly by `business_id`. Top-10 semantic neighbors.
- **FR-302 (Sparse Lexical Retrieval)**:
  - `rank-bm25` index per business tenant. Exact keyword, acronym, pricing, and policy terms matching. Top-10 lexical hits.
- **FR-303 (Reciprocal Rank Fusion - RRF)**:
  - Merges Dense and Sparse lists using $RRF(d) = \sum \frac{1}{60 + \text{rank}(d)}$. Deduplicates and ranks top-5 candidate chunks.

### 4.4 Module 4: `decision-gate-and-llm` (Less AI-Dependent)
- **FR-401 (Pre-LLM Confidence Circuit Breaker)**:
  - If top candidate RRF/similarity score $< \text{THRESHOLD}$:
    - **Do NOT call LLM API**.
    - Immediately return business fallback message: *"I don't have this information in my documents. I've logged this question for our team."*
    - Persist query to `unanswered_questions` table (`is_answered = False`).
- **FR-402 (Greeting Interceptor)**:
  - Fast regex for common greetings ("hi", "hello", "thanks") returning instant friendly canned replies.
- **FR-403 (Multi-Tier LLM Cascade)**:
  - *Tier 1 (Primary)*: Google Gemini 1.5/2.0 Flash (free tier: 15 RPM, 1M TPM).
  - *Tier 2 (Fallback)*: Groq Llama 3.1 8B / 3.2 3B Instant (free tier: 30 RPM, 300+ tok/s).
- **FR-404 (Deterministic Citations & Source Preview)**:
  - API attaches chunk metadata (`document_name`, `page_number`, `chunk_id`, `text_excerpt`) directly to the response payload.
  - Customer can click the badge to preview the exact chunk text.

### 4.5 Module 5: `chat-service`
- **FR-501 (Multi-Turn Chat)**: Manages conversation sessions with rolling context (last 4 message pairs).
- **FR-502 (Answer Feedback)** ⭐:
  - Customer can click 👍 or 👎 on any assistant message.
  - Endpoint `POST /api/chat/message/:id/feedback` updates `feedback: 'up' | 'down'`.
- **FR-503 (Lead Capture / Human Handoff)** ⭐:
  - When assistant triggers fallback, UI displays: *"Want us to get back to you? Leave your email."*
  - Endpoint `POST /api/chat/session/:id/lead` saves customer email to `unanswered_questions`.
- **FR-504 (Streaming SSE)**:
  - Endpoint `POST /api/chat/stream` streams tokens word-by-word via Server-Sent Events.
- **FR-505 (Embeddable Widget)** ⭐:
  - Standalone script `widget.js` that any business owner can paste on their website to inject a floating chat widget.

### 4.6 Module 6: `owner-dashboard`
- **FR-601 (Analytics Overview)**:
  - Metrics: Total Chats, Total Questions, Answered vs Unanswered Count, Resolution Rate (%), Average Latency (ms).
  - Extra charts: Top asked questions, Most cited documents, Downvoted answers review.
- **FR-602 (Unanswered Questions & Resolver Loop)** ⭐:
  - Table of all unanswered questions with frequency count and captured customer emails.
  - **"Answer & Add to Knowledge Base" Modal**: Owner types the answer $\rightarrow$ creates `manual_qa` document $\rightarrow$ embeds into vector/BM25 store $\rightarrow$ marks question as resolved!
- **FR-603 (Chat History & Feedback Filter)**:
  - Browse past chat sessions.
  - Toggle filter: "Show only chats with downvoted answers (👎)" for rapid quality debugging.
- **FR-604 (Test Playground)** ⭐:
  - Interactive testing sandbox where the owner queries the assistant and inspects:
    - Retrieved chunks with similarity scores.
    - Sparse vs Dense ranks.
    - LLM generation time and provider used.

---

## 5. Technical Specifications & Database Schema

```mermaid
erDiagram
    BUSINESS ||--o{ USER : has
    BUSINESS ||--o{ DOCUMENT : owns
    BUSINESS ||--o{ CHAT_SESSION : hosts
    BUSINESS ||--o{ UNANSWERED_QUESTION : logs
    DOCUMENT ||--o{ DOCUMENT_CHUNK : contains
    CHAT_SESSION ||--o{ CHAT_MESSAGE : contains

    BUSINESS {
        string id PK "uuid"
        string name "Organization Name"
        string slug UK "Unique URL Slug"
        string share_token UK "Public Share UUID"
        string tone "friendly | formal"
        string brand_color "Hex color code"
        text fallback_message
        json starter_questions "List of strings"
        datetime created_at
    }

    USER {
        string id PK "uuid"
        string business_id FK
        string email UK
        string password_hash
        string role "owner | customer"
        datetime created_at
    }

    DOCUMENT {
        string id PK "uuid"
        string business_id FK
        string file_name
        string file_type "pdf | docx | txt | manual_qa"
        string storage_path
        int file_size_bytes
        int chunk_count
        string status "QUEUED | PROCESSING | INDEXED | FAILED"
        string parser_used "sarvam | pymupdf | manual"
        datetime created_at
        datetime updated_at
    }

    DOCUMENT_CHUNK {
        string id PK "uuid"
        string document_id FK
        string business_id FK
        int chunk_index
        int page_number
        text content
        json metadata_payload
    }

    CHAT_SESSION {
        string id PK "uuid"
        string business_id FK
        string customer_id FK "nullable"
        string customer_email "nullable for lead capture"
        string channel "public_link | widget | portal"
        datetime started_at
        datetime last_message_at
    }

    CHAT_MESSAGE {
        string id PK "uuid"
        string session_id FK
        string sender "customer | assistant | system"
        text content
        boolean is_answered
        string feedback "up | down | null"
        json source_citations
        float confidence_score
        int latency_ms
        string llm_provider_used
        datetime created_at
    }

    UNANSWERED_QUESTION {
        string id PK "uuid"
        string business_id FK
        string session_id FK
        string message_id FK
        text question_text
        string customer_email "nullable"
        float top_retrieval_score
        boolean is_resolved
        text resolved_answer "Answer provided by owner"
        datetime resolved_at
        datetime created_at
    }
```

---

## 6. API Endpoint Contracts

### 6.1 Authentication & Settings (`/api/auth`, `/api/business`)
- `POST /api/auth/register` — Register owner/customer.
- `POST /api/auth/login` — Login and get JWT.
- `GET  /api/business/settings` — Get owner's business settings & share links.
- `PUT  /api/business/settings` — Update tone, brand color, fallback text, starter questions.

### 6.2 Document Ingestion (`/api/documents`)
- `POST /api/documents/upload` — Multipart file upload (`HTTP 202 Accepted`).
- `POST /api/documents/manual-qa` — Create a manual Q&A document chunk from resolved question.
- `GET  /api/documents` — List documents with chunk counts and statuses.
- `DELETE /api/documents/:id` — Delete document and re-index.

### 6.3 Chat, Feedback & Widget (`/api/chat`, `/api/public`)
- `GET  /api/public/business/:slug` — Public metadata for chat widget & standalone link.
- `POST /api/chat/message` — Send query, get answer + source citations.
- `POST /api/chat/stream` — SSE token-by-token streaming.
- `POST /api/chat/message/:id/feedback` — Submit thumbs up (`up`) or thumbs down (`down`).
- `POST /api/chat/session/:id/lead` — Submit customer email for human handoff.

### 6.4 Owner Dashboard & Playground (`/api/dashboard`)
- `GET  /api/dashboard/stats` — Total chats, questions, answered/unanswered counts, avg latency.
- `GET  /api/dashboard/unanswered` — Paginated list of unanswered questions.
- `POST /api/dashboard/unanswered/:id/resolve` — Resolve question and automatically index answer.
- `GET  /api/dashboard/chats` — Chat session explorer with `?filter=downvoted` option.
- `POST /api/dashboard/playground` — Test query with debug metrics (retrieved chunks, scores, RRF ranks).

---

## 7. Phased Implementation Roadmap & Commit Attribution

```mermaid
gantt
    title Phased Engineering Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 0: Scaffolding
    Git Setup, BRD, PRD & Base Repos Clean   :p0, 2026-11-01, 1d
    section Phase 1: Core & Multi-Tenancy
    SQLAlchemy Models, JWT RBAC, Settings API :p1, after p0, 1d
    section Phase 2: Ingestion & Q&A Resolver
    Sarvam API + PyMuPDF Fallback + Queue    :p2_1, after p1, 1d
    Manual Q&A Ingestion Engine (Resolver)   :p2_2, after p2_1, 1d
    section Phase 3: Hybrid RAG & Cascade
    Chroma Dense + BM25 Sparse + RRF Index  :p3_1, after p2_2, 1d
    Pre-LLM Circuit Breaker & Gemini/Groq   :p3_2, after p3_1, 1d
    section Phase 4: Customer Chat & Widget
    Chat API, SSE Stream, Source Preview    :p4_1, after p3_2, 1d
    Thumbs Up/Down Feedback & Lead Capture  :p4_2, after p4_1, 1d
    Public Link & Embeddable Widget Snippet :p4_3, after p4_2, 1d
    section Phase 5: Owner Dashboard & Playground
    Analytics Cards, Downvote Filter        :p5_1, after p4_3, 1d
    Resolve Unanswered Modal & Playground   :p5_2, after p5_1, 1d
    section Phase 6: E2E Verification & Release
    Seed Script, Evaluation Checks & Docker :p6, after p5_2, 1d
```

| Phase | Core Deliverables | Git Author Attribution |
| :--- | :--- | :--- |
| **Phase 0** | Git init, `.gitignore`, [BRD.md](file:///c:/Users/datta.000/Desktop/IDEVIFY/BRD.md), [PRD.md](file:///c:/Users/datta.000/Desktop/IDEVIFY/PRD.md), [README.md](file:///c:/Users/datta.000/Desktop/IDEVIFY/README.md) | `Nishant Datta <dattanishant2@gmail.com>` |
| **Phase 1** | Multi-tenant schema, SQLite dev $\rightarrow$ Postgres prod, JWT RBAC, Business settings & starter questions | `Nishant Datta <dattanishant2@gmail.com>` |
| **Phase 2** | **Sarvam Document Intelligence API** + **PyMuPDF fallback**, async queue worker, chunking, and **Manual Q&A ingestion** | **`Ishwari Bhoyar <ishwaribhoyar2@gmail.com>`** |
| **Phase 3** | **Multi-Hybrid RAG** (ChromaDB + BM25 + RRF), **Laya System 1 Neural Guardrails**, **Pre-LLM Confidence Circuit Breaker**, **Gemini Flash $\rightarrow$ Groq Llama cascade** | **`Ishwari Bhoyar <ishwaribhoyar2@gmail.com>`** |
| **Phase 4** | Customer chat API, SSE streaming, **Answer Feedback (👍/👎)**, **Lead Capture form**, **Source chunk preview**, **Embeddable Widget** | `Ishwari Bhoyar <ishwaribhoyar2@gmail.com>` & `Nishant Datta` |
| **Phase 5** | Analytics Dashboard, **Resolve Unanswered Questions into Knowledge Base**, Downvote filter, **Test Playground** | `Nishant Datta <dattanishant2@gmail.com>` |
| **Phase 6** | Sample business seeder (`seed.py`), 4-point Idevify evaluation verification suite, Render deployment configuration | Joint Final Release |

---

## 8. Multi-Device Authentication & Analytics Telemetry Specs

### 8.1 Cross-Device Identity Synchronization
- Seamless workspace recovery via `/api/auth/active-owner` and `/api/auth/session/validate`.
- Case-insensitive email normalization across registration and sign-in handlers.
- Auto-redirect and session persistence preventing data fragmentation across mobile and desktop devices.

### 8.2 Power BI / Excel Live Connector Architecture
- Direct streaming `/api/dashboard/export/powerbi?format=csv` with UTF-8 BOM (`\ufeff`) compatibility.
- Transparent query token authentication (`?token=...`) supporting automated enterprise scheduled refreshes.
- Response headers `X-Dataset-Rows` and `X-Dataset-Schema-Version` for ETL ingestion pipelines.
