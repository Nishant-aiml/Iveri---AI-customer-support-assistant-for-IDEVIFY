# AI Customer Support Assistant (RAG Platform)

> **Client / Assessment**: Idevify Solutions Private Limited  
> **Project Type**: Multi-Tenant Retrieval-Augmented Generation (RAG) Web Application  
> **Target Audience**: Small Business Owners & their Customers  

---

## 📌 Executive Summary & Problem Statement

Small businesses routinely receive repetitive customer inquiries regarding core operations—such as pricing, return/refund policies, business hours, and delivery timelines. Dedicating human staff to continuously answer identical queries is inefficient and costly. Conversely, generic out-of-the-box chatbots frequently hallucinate or generate incorrect information because they lack business-specific context.

**The Solution:**  
A purpose-built web platform enabling business owners to upload their proprietary knowledge base documents (PDF, DOCX, TXT). The system ingests and indexes these files, generating an AI customer support assistant accessible via a dedicated customer portal or shareable public link. 

The assistant answers questions **strictly and exclusively** from the uploaded documents, cites sources, avoids hallucinations with polite fallbacks, and logs unanswered questions to an owner dashboard for continuous knowledge base improvements.

---

## 🏗️ System Architecture & Workflow

```mermaid
flowchart TD
    subgraph Knowledge_Ingestion["1. Knowledge Ingestion Pipeline"]
        Owner["Business Owner"] -->|Uploads PDF, DOCX, TXT| DocMgmt["Document Manager API"]
        DocMgmt -->|Extract Text & Chunk| Chunker["Text Chunker & Metadata Tagger"]
        Chunker -->|Generate Embeddings| EmbeddingModel["Embedding Model (e.g. OpenAI / Gemini)"]
        EmbeddingModel -->|Store Vector + Payload| VectorDB[("Vector Database / pgvector")]
        DocMgmt -->|Store Metadata| RelationalDB[("Relational DB (PostgreSQL/SQLite)")]
    end

    subgraph Chat_RAG_Flow["2. RAG & Query Pipeline"]
        Customer["Customer / Public User"] -->|Ask Question| ChatAPI["Chat Service"]
        ChatAPI -->|Embed Query| QueryEmbedding["Query Embedding"]
        QueryEmbedding -->|Similarity Search (cosine)| VectorDB
        VectorDB -->|Top-k Document Chunks| PromptBuilder["Context & Prompt Builder"]
        PromptBuilder -->|Strict Grounded Prompt| LLM["LLM (GPT-4o-mini / Gemini Flash)"]
        
        LLM -->|Answers with Source Citation| ChatAPI
        LLM -.->|No context found / Unknown| FallbackHandler["Polite Fallback: 'I don't have this info'"]
        FallbackHandler -->|Log Unanswered Query| UnansweredLog[("Unanswered Questions Table")]
        ChatAPI -->|Display Answer + Source| Customer
    end

    subgraph Analytics_Dashboard["3. Business Owner Dashboard"]
        Owner -->|Inspect| DashView["Owner Portal"]
        DashView -->|Fetch Analytics| StatsAPI["Dashboard Service"]
        StatsAPI --> RelationalDB
        StatsAPI --> UnansweredLog
        DashView --> TotalChats["Total Chats & Questions"]
        DashView --> AnsRatio["Answered vs. Unanswered Rate"]
        DashView --> UnansweredList["Actionable Unanswered Questions List"]
    end
```

---

## 🚀 Key Features

### 1. Authentication & Role-Based Access Control (RBAC)
- **Business Owner**: Full access to upload/manage documents, view all chat logs, review unanswered questions, and monitor the analytics dashboard.
- **Customer**: Authenticated user experience for registered customers.
- **Public Shareable Chat Link**: Direct, frictionless access for external customers via a business-specific URL token (e.g., `/chat/:businessSlug` or `/chat/share/:shareToken`).
- **Strict Multi-Tenancy**: Complete data isolation across businesses. An owner can only inspect and query their own documents and chat transcripts.

### 2. Knowledge Base & Document Processing
- **File Format Support**: PDF, DOCX, and TXT files.
- **Content Ingestion**:
  - Text extraction with clean formatting.
  - Semantic/recursive chunking (recommended chunk size: ~500–1000 tokens with 10–20% overlap).
  - Metadata enrichment (document name, chunk index, timestamp, business ID).
- **CRUD Operations**: Upload, view, re-upload/update, and delete documents. Deleting or updating a document instantly updates or invalidates corresponding chunks in the vector index.

### 3. Retrieval-Augmented Generation (RAG) & Grounding
- **Dense Vector Search**: Semantic similarity matching (cosine distance) between customer queries and document chunk embeddings.
- **Strict Source Grounding**: System prompts explicitly constrain the LLM to answer only using the retrieved context snippets.
- **Citations & Transparency**: Every answer displays the source document name (and page/section where applicable) from which the context was retrieved.

### 4. Hallucination Prevention & Unanswered Query Handling
- **Polite Unknown Fallback**: When the query cannot be answered with high confidence from the retrieved context, the assistant responds with a polite fallback:
  > *"I don't have this information in my current knowledge base. I've logged this question for our team to assist you further."*
- **Automatic Question Logging**: Unanswered questions are persisted to the database and flagged for the owner.
- **Fault-Tolerant Error Handling**: Graceful degradation when external LLM or vector APIs experience rate limits, network interruptions, or failures.

### 5. Chat History & Conversation Persistence
- Stores full conversation threads (sessions, messages, role: customer/assistant, timestamps, retrieved source metadata).
- Allows business owners to review customer interactions to gauge user intent, satisfaction, and recurring inquiries.

### 6. Analytics & Owner Dashboard
- **Total Chats**: Total chat sessions initiated.
- **Total Questions**: Cumulative number of questions asked.
- **Answered vs. Unanswered Ratio**: Clear breakdown of queries successfully resolved vs. flagged as unknown.
- **Actionable Gap Analysis**: List of unanswered questions, providing business owners with direct insights into what documentation needs to be added or updated.

---

## 🗄️ Database & Domain Model

```mermaid
erDiagram
    BUSINESS ||--o{ USER : contains
    BUSINESS ||--o{ DOCUMENT : owns
    BUSINESS ||--o{ CHAT_SESSION : receives
    BUSINESS ||--o{ UNANSWERED_QUESTION : logs
    DOCUMENT ||--o{ DOCUMENT_CHUNK : produces
    CHAT_SESSION ||--o{ CHAT_MESSAGE : contains

    BUSINESS {
        uuid id PK
        string name
        string slug
        string share_token UK
        timestamp created_at
    }

    USER {
        uuid id PK
        uuid business_id FK
        string email UK
        string password_hash
        string role "OWNER | CUSTOMER"
        timestamp created_at
    }

    DOCUMENT {
        uuid id PK
        uuid business_id FK
        string file_name
        string file_type "pdf | docx | txt"
        string file_url
        int chunk_count
        timestamp created_at
        timestamp updated_at
    }

    DOCUMENT_CHUNK {
        uuid id PK
        uuid document_id FK
        uuid business_id FK
        text content
        int chunk_index
        vector embedding "1536d / 768d"
        jsonb metadata
    }

    CHAT_SESSION {
        uuid id PK
        uuid business_id FK
        uuid customer_id FK "nullable for anonymous/public"
        timestamp started_at
    }

    CHAT_MESSAGE {
        uuid id PK
        uuid session_id FK
        string sender "customer | assistant | system"
        text content
        jsonb source_references
        boolean is_answered
        timestamp created_at
    }

    UNANSWERED_QUESTION {
        uuid id PK
        uuid business_id FK
        uuid message_id FK
        text question_text
        timestamp logged_at
        boolean resolved
    }
```

---

## 🛠️ Recommended Technology Stack

| Layer | Recommended Tools / Frameworks | Alternatives |
| :--- | :--- | :--- |
| **Frontend** | **Next.js (React)**, Tailwind CSS, Lucide React, Shadcn UI | React + Vite, Vue 3 |
| **Backend API** | **FastAPI (Python)** or **Next.js API / Route Handlers** | Express.js, NestJS |
| **Relational Database** | **PostgreSQL** (with Prisma or SQLAlchemy) | SQLite (Dev) / Supabase |
| **Vector Store** | **pgvector** (PostgreSQL extension) or **ChromaDB** | Pinecone, Qdrant, Weaviate |
| **Embeddings & LLM** | **OpenAI** (`text-embedding-3-small`, `gpt-4o-mini`) | **Google Gemini** (`gemini-1.5-flash`, `text-embedding-004`) |
| **Document Parsers** | `pdfplumber` / `pypdf` (PDF), `python-docx` (DOCX), standard text I/O | LangChain / LlamaIndex parsers |
| **Authentication** | NextAuth.js / JWT Auth / Supabase Auth | Clerk, Firebase Auth |

---

## 🔒 Evaluation Criteria Alignment Checklist

| Criteria | Implementation Strategy |
| :--- | :--- |
| **1. Document Upload & Extraction** | Direct parsing of `.pdf`, `.docx`, and `.txt` files with clean chunking and validation on size and MIME type. |
| **2. Relevant Chunk Retrieval & Sourcing** | Vector similarity (Cosine/Dot Product) search scoped strictly by `business_id`; answers return citation badges pointing to specific uploaded files. |
| **3. Zero Hallucinations & Error Resilience** | Strict system prompts specifying *"Answer only using the provided context. If unknown, output fallback code/message"*; automated database logging for unknown queries; try/catch fallback handlers for LLM API limits. |
| **4. Multi-Tenant Data Isolation** | Every query, document, chat session, and vector index is tagged with `business_id`. Cross-tenant querying is prevented at the database and retrieval layers. |

---

## 📋 API Design Overview

### Authentication & Setup
- `POST /api/auth/register` — Register a new business owner or customer.
- `POST /api/auth/login` — Login and receive JWT / session cookie.
- `GET  /api/business/me` — Retrieve the current business profile, settings, and shareable link token.

### Document Management
- `POST /api/documents/upload` — Upload `.pdf`, `.docx`, or `.txt` file; triggers extraction and vector embedding.
- `GET  /api/documents` — List all uploaded documents with metadata (name, chunks, upload date).
- `DELETE /api/documents/:id` — Delete a document and purge all associated chunks from the vector store.
- `PUT  /api/documents/:id` — Replace/update an existing document and re-index.

### Customer Chat & RAG
- `POST /api/chat/message` — Send a question within a chat session (returns answer + source document citations).
- `GET  /api/chat/public/:shareToken` — Resolve public customer chat interface for a specific business.
- `GET  /api/chat/history/:sessionId` — Fetch chat transcript for a session.

### Owner Dashboard & Analytics
- `GET  /api/dashboard/stats` — Summary metrics: total chats, total questions, answered count, unanswered count.
- `GET  /api/dashboard/unanswered` — Retrieve paginated list of unanswered customer queries.
- `GET  /api/dashboard/chats` — Review all customer chat sessions and full transcripts.

---

## ⚡ Setup & Local Development (Guide)

### 1. Prerequisites
- **Node.js** (v18+ or v20+)
- **Python** (3.10+ if using FastAPI/Python backend) or Node.js runtime
- **PostgreSQL** with `pgvector` enabled (or a managed Supabase / ChromaDB instance)
- **API Key**: OpenAI (`OPENAI_API_KEY`) or Google Gemini (`GEMINI_API_KEY`)

### 2. Environment Variables (`.env.example`)
```env
# Database
DATABASE_URL="postgresql://user:password@localhost:5432/idevify_rag"

# LLM & Embeddings Provider
OPENAI_API_KEY="sk-..."
# or
GEMINI_API_KEY="..."

# Vector DB (if separate)
VECTOR_DB_URL=""

# Authentication
JWT_SECRET="your-super-secret-jwt-key"
NEXTAUTH_SECRET="your-nextauth-secret"
NEXTAUTH_URL="http://localhost:3000"
```

### 3. Recommended Project Structure
```text
IDEVIFY/
├── AI Customer Support.pdf        # Original assessment requirement document
├── README.md                      # Project documentation and context
├── apps/ (or src/)
│   ├── web/                       # Next.js / React Frontend
│   │   ├── components/            # UI components (ChatWidget, DocUploader, Dashboard)
│   │   ├── pages/ or app/         # App router (auth, dashboard, chat, share)
│   │   └── lib/                   # API clients and utilities
│   └── api/ (or backend/)         # Backend RAG & Data Engine
│       ├── routers/               # auth, documents, chat, dashboard
│       ├── services/
│       │   ├── parser.py          # PDF/DOCX/TXT extraction
│       │   ├── chunker.py         # Text chunking logic
│       │   ├── vector_store.py    # Vector store indexing & search
│       │   └── rag_engine.py      # Prompt construction & LLM invocation
│       └── models/                # Database entities & schemas
```

---

## 💡 Prompt Strategy for Strict Grounding

```text
You are an AI Customer Support Assistant for {business_name}.
Your job is to answer the customer's question STRICTLY and ONLY using the provided document excerpts below.

Context Excerpts:
---------------------
{retrieved_chunks}
---------------------

Instructions:
1. If the answer is directly supported by the context above, provide a helpful and clear answer.
2. Always reference the source document name where the answer was found.
3. If the answer CANNOT be determined from the context above, do NOT make up an answer or speculate. Respond EXACTLY with:
   "I'm sorry, but I do not have this information in my documents. I have logged your question for the business owner to review."
4. Do not mention "context excerpts" or "documents provided" directly in the conversation tone; speak as the support assistant.
```

---

## 📅 Delivery Timeline & Milestones (5-Day Plan)

- **Day 1: Project Setup & Authentication**
  - Scaffold repository, setup DB schema, implement RBAC auth (Owner vs Customer), public shareable link routing.
- **Day 2: Document Pipeline & Vector Indexing**
  - Build file uploader for PDF/DOCX/TXT; implement text extraction, chunking, embedding generation, and vector persistence.
- **Day 3: Retrieval & Grounded RAG Chat Engine**
  - Implement vector similarity search scoped to tenant; build strict LLM prompt pipeline with citation attribution and unknown fallback handling.
- **Day 4: Logging & Owner Dashboard**
  - Implement chat history viewer, unanswered questions logger, and metric summary cards (total chats, total questions, answered vs unanswered).
- **Day 5: Testing, Hardening & Deployment**
  - End-to-end testing with varied test documents; test edge cases (empty documents, irrelevant queries, API error simulation); finalize documentation and containerize/deploy.
