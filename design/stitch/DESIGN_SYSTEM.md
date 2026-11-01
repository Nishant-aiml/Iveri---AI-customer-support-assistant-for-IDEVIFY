# Obsidian Kinetic — Design System & Stitch Prototypes

> **Generated with Google Stitch MCP Server**  
> **Stitch Project ID:** `113009803571435662`  
> **Project Resource:** `projects/113009803571435662`  
> **Design System ID:** `assets/ff0da0498d914bfebae7ba020d3fef78`  
> **Theme Philosophy:** Ultra-Refined Dark Mode with Precision Instrument Minimalism

---

## 1. Design System Overview

The **Obsidian Kinetic** design system projects surgical precision, sovereign intelligence, and understated power. Engineered for Tier-1 engineering operations and high-density customer support consoles, it avoids consumer AI gimmicks in favor of high-density clarity inspired by professional developer consoles and institutional analytics.

- **Tone**: Focused, authoritative, calm, high-velocity.
- **Visual Weight**: Deep pitch-black and deep obsidian backdrops punctuated by razor-thin, photon-catching micro-borders (`1px solid #1F2438`).
- **Accents**: 
  - **Electric Indigo (`#6366F1`)**: Generative computation and primary actions.
  - **Emerald (`#10B981`)**: Deterministic verification, grounded source citations, and nominal system state.
  - **Violet (`#8B5CF6`)**: Autonomous reasoning and AI processing tags.
  - **Amber (`#F59E0B`)**: Degraded state, confidence anomaly, and unanswered inquiry warnings.
  - **Rose (`#F43F5E`)**: Downvoted answer reporting and error highlights.

---

## 2. Design Tokens

### Color Palette
| Token | Hex Value | Semantic Usage |
| :--- | :--- | :--- |
| `background` | `#090A0F` | Deep canvas surface |
| `surface` | `#0D0F17` | App bar, header, inputs, and recessed containers |
| `surface-container` | `#131622` | Instrument cards, floating panels, dialogs |
| `surface-container-high` | `#1E2438` | Hover states and elevated cards |
| `outline-variant` | `#1F2438` | Micro-borders (1px sub-pixel boundaries) |
| `primary` | `#6366F1` | Electric Indigo brand accent & primary CTAs |
| `secondary` | `#8B5CF6` | Violet reasoning & auxiliary indicators |
| `tertiary` | `#10B981` | Emerald verification & grounded citation badges |
| `on-surface` | `#E2E1ED` | High-contrast body text |
| `on-surface-variant` | `#94A3B8` | Subtle metadata and captions |

### Typography
- **Headlines & Body**: `Geist` (`400`, `500`, `600`, `700`)
- **Metrics, Latency & Citations**: `JetBrains Mono` (`400`, `500`, `600`)

### Elevation & Materiality
- **Level 0 (Canvas)**: `#090A0F` flat background.
- **Level 1 (Recessed Container)**: `#0D0F17` + `1px solid #1F2438`.
- **Level 2 (Instrument Glass)**: `#131622` + `1px solid #1F2438` + `box-shadow: inset 0 1px 0 0 rgba(255, 255, 255, 0.05)`.
- **Level 3 (Modal / Overlays)**: `#131622` (95% opacity) + `backdrop-filter: blur(16px)` + `border: 1px solid #1F2438`.

---

## 3. Stitch Screens Catalog

### Screen 1: Owner Analytics & Knowledge Base Dashboard
- **Screen ID**: `4dfb94ac7a6e44d4b42e93a304619e75`
- **HTML Artifact**: `design/stitch/stitch_dashboard.html`
- **Raw Metadata**: `design/stitch/stitch_dashboard_raw.json`
- **Key Modules**:
  - Live Tenant Status Pill with pulsing green beacon
  - Top 5 KPI Metrics: Total Chats, Inquiries, Resolution Rate, Unanswered Queue, RAG Avg Latency
  - Dual-Engine Document Ingestion (Sarvam Doc AI + PyMuPDF)
  - Unanswered Questions closed-loop 1-click resolution
  - Conversation Quality Audit with downvote filtering
  - RAG Playground with BM25 + Dense ChromaDB score diagnostics

### Screen 2: Public Customer Support Chat & Embeddable Widget
- **Screen ID**: `7622ca1ba97c40b5abc65c23ad609967`
- **HTML Artifact**: `design/stitch/stitch_screen2_extracted.html`
- **Raw Metadata**: `design/stitch/stitch_screen2.html`
- **Key Modules**:
  - Customer Chat Console with verified grounding badges
  - Monospace latency indicator (`142ms · Gemini Flash`)
  - Interactive Citation Drawer with source text and page attribution
  - Thumbs up/down feedback buttons with instant vote recording
  - Suggested starter question pill buttons
  - Automatic lead capture handoff when out of domain
  - Floating embeddable website widget `<script>` preview
