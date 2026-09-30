# InvoiceShield AutoGen — P2P Invoice Validation & Automation

A production-grade AI-powered invoice validation system for enterprise P2P (Procure-to-Pay) workflows. Built for Rane (Madras) Limited Plant 4, InvoiceShield automates GST compliance, vendor verification, and invoice approval decisions with a 10-agent autonomous pipeline.

---

## 🎯 The Problem

Manual invoice processing is slow, error-prone, and expensive. Finance teams waste hours on:

- ✗ Vendor verification against master lists
- ✗ GST validation and compliance checks
- ✗ PO matching and duplicate detection
- ✗ HSN code and rate validation
- ✗ ITC eligibility assessment
- ✗ Price variance flagging
- ✗ Audit trail maintenance

**Result:** 7-14 day processing cycles, compliance risks, and poor visibility.

---

## ✨ The Solution

InvoiceShield is an autonomous 10-agent system that validates invoices in **~1.4 seconds** and routes them to the right approver based on risk and amount:

- ✅ **AUTO-APPROVE** simple invoices (< ₹50K, no flags)
- 🔍 **HUMAN-REVIEW** flagged items for expert judgment
- ❌ **AUTO-REJECT** blacklisted vendors, duplicates, and invalid data

The system integrates real PDF extraction, live validation logic, and intelligent decision routing—all with full audit trails and compliance evidence.

---

## 🏗️ Architecture

### Frontend (Next.js 14 + React)

📱 Modern, responsive UI with:

- **Dashboard Tab** — KPI cards (total invoices, vendors, approval rates, top vendors)
- **Upload Tab** — Drag-drop PDF upload with real-time file validation
- **Pipeline Tab** — Animated 10-agent visualization with staggered agent execution (80ms per agent)
- **Results Tab** — Expandable decision details, agent report, vendor audit, price cop analysis, PDF text preview
- **History Tab** — Sortable table with invoice metadata and approval status

**Tech:** TypeScript, Tailwind CSS, React Hooks, parallel data fetching, state management with useCallback.

### Backend (FastAPI + Python)

🚀 High-performance validation engine:

- **Real PDF Extraction** — pdfplumber + regex-based field extraction (invoice #, vendor, GSTIN, amount, PO, HSN, GST rate, date)
- **10 Autonomous Agents** — Each specializes in one validation domain
- **Intelligent Routing** — Amount-based and risk-based approval delegation
- **Fallback Mechanism** — Known sample data fills missing PDF fields (with transparency)
- **Price Tracking** — Baseline calculation and variance flagging (>20% = CRITICAL, >10% = WARNING)
- **Duplicate Detection** — File hash + invoice key + exact match checks
- **Audit Trail** — Complete decision history with agent findings

**Tech:** FastAPI, pdfplumber, regex, in-memory caching, parallel processing.

---

## 🤖 The 10 Validation Agents

1. **Vendor Verification** — Checks vendor master, blacklist, contract validity
2. **GST Validation** — Format check, state code (01-38), GSTIN structure
3. **Amount Check** — Positive value, within limits, reasonableness
4. **PO Verification** — Presence check, duplicate detection, PO/YYYY/NNN format
5. **HSN Validation** — Catalog lookup, invalid/dummy code detection
6. **GST Rate Check** — Match vs HSN_GST_MAP, rate consistency
7. **ITC Eligibility** — Approved vendor + amount ≥ ₹500 check
8. **Duplicate Detection** — File hash, invoice key (GSTIN+InvNo), exact duplicate
9. **Audit Trail** — AUDIT_FINDINGS lookup (CLEAN/MEDIUM_RISK/HIGH_RISK)
10. **Price Cop** — Variance tracking, baseline comparison, spike detection

⚡ **Result:** Comprehensive risk scoring in ~1.4 seconds with full transparency.

---

## 🎯 Approval Decision Logic

```
┌─ CRITICAL Issues Found?
├─ YES → AUTO-REJECT (SYSTEM)
└─ NO → Check Amount:
   ├─ > ₹500,000 → HUMAN-REVIEW (PLANT_HEAD)
   ├─ ≥ ₹100,000 → HUMAN-REVIEW (PROCUREMENT_HEAD)
   ├─ ≥ ₹50,000 OR any flagged issue → HUMAN-REVIEW (FINANCE_MANAGER)
   └─ < ₹50,000 & CLEAN → AUTO-APPROVE (SYSTEM)
```

💡 **Key:** Rejected invoices do NOT consume PO limits or pollute price baselines.

---

## 📊 Sample Test Results

✅ **sample_1_normal.pdf** → AUTO-APPROVE
- Amount: ₹47,200 | Vendor: Priya Electrical | No flags

🔍 **sample_2_high_value.pdf** → HUMAN-REVIEW (PLANT_HEAD)
- Amount: ₹7,50,000 | Vendor: Premium Components | High-value threshold

❌ **sample_3_blacklisted.pdf** → AUTO-REJECT
- Vendor: Bangalore IT Solutions | BLACKLISTED status

⚠️ **sample_4_price_spike.pdf** → HUMAN-REVIEW (FINANCE_MANAGER)
- Amount: ₹92,040 | Price spike: 30% increase (₹4K → ₹5.2K) | PRICE_CRITICAL flag

🚫 **sample_5_duplicate_po.pdf** → AUTO-REJECT
- PO: PO/2026/0001 (used twice) | DUPLICATE_PO violation

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- pip & npm
- OPENAI_API_KEY in .env

### Installation & Setup

```bash
# Clone or unzip project
cd D:\Invoiceshield_p2p

# Backend setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install pdfplumber python-multipart

# Frontend setup
cd invoiceshield-ui
npm install

# Create .env in project root
echo OPENAI_API_KEY=sk-your-key-here > .env
```

### Running the System

**Terminal 1 (Backend):**
```bash
cd D:\Invoiceshield_p2p
venv\Scripts\activate
python src/fastapi_server.py
```
→ Runs on http://127.0.0.1:8000

**Terminal 2 (Frontend):**
```bash
cd D:\Invoiceshield_p2p\invoiceshield-ui
npm run dev
```
→ Runs on http://localhost:3000

✅ Open browser: http://localhost:3000

### API Endpoints

**GET /health**
System status check
```json
{"status": "running"}
```

**GET /system-stats**
Real-time KPIs
```json
{
  "invoices_processed": 5,
  "unique_pos": 4,
  "auto_approved": 1,
  "human_review": 2,
  "auto_rejected": 2,
  "total_value": "₹9,22,340",
  "avg_processing_ms": 1420,
  "success_rate": "100%",
  "top_vendors": [{"name": "Priya Electrical", "count": 3, "total": "₹2,17,140"}]
}
```

**POST /upload-invoice** (multipart/form-data)
Upload and validate PDF
- Request: PDF file
- Response: Full validation result with agent findings

**GET /invoice-history**
All processed invoices (newest first)
- Response: List of invoice records with decision and timestamp

**GET /price-history**
Price tracking baseline and variance data
- Response: Vendor pricing history for cost analysis

**POST /reset-system**
Clear all data (development only)
- Response: {"status": "system_reset"}

---

## 🔧 Tech Stack

**Backend:**
- FastAPI — Async REST API framework
- pdfplumber — PDF text extraction
- Python regex — Field extraction
- In-memory caching — Fast lookups

**Frontend:**
- Next.js 14 — React framework
- TypeScript — Type safety
- Tailwind CSS — Styling
- React Hooks — State management

**Infrastructure:**
- Runs locally on Windows/Mac/Linux
- No database required (in-memory state)
- Can deploy to Hostinger VPS (187.53.139.17)

---

## 📦 Project Structure

```
Invoiceshield_p2p/
├── src/
│   ├── fastapi_server.py       # Main backend + 10 agents
│   ├── requirements.txt         # Python dependencies
│   └── data/
│       ├── vendor_master.json   # Approved vendors + GSTIN
│       ├── hsn_gst_map.json     # HSN to GST rate mapping
│       └── known_samples.json   # Fallback data for known PDFs
├── invoiceshield-ui/
│   ├── app/
│   │   └── page.tsx             # Main React component
│   ├── package.json
│   └── next.config.js
├── .env                         # API keys (gitignore'd)
├── .gitignore
└── README.md                    # This file
```

---

## 🎓 What This Demonstrates

### For Finance Professionals:

✅ P2P workflow automation
✅ GST compliance automation
✅ Vendor master management
✅ Invoice validation at scale
✅ ITC eligibility calculation
✅ Price variance tracking
✅ Audit trail & compliance evidence

### For GenAI Engineers:

✅ Multi-agent autonomous systems
✅ PDF text extraction (real documents)
✅ Regex-based data parsing
✅ Decision logic & routing
✅ FastAPI async handling
✅ Real-time frontend state sync
✅ Animated UI with React
✅ Production error handling

### For Portfolio:

✅ End-to-end system design
✅ Business case alignment
✅ Production-grade code
✅ Real PDF data processing
✅ Compliance & audit focus

---

## 💡 Key Features

🎯 **Smart Routing**
Automatic approval/review/rejection based on amount and risk

⚡ **Fast Processing**
~1.4 seconds per invoice (PDF extraction + 10 agents + decision)

🔍 **Transparent Results**
Full agent reports, vendor audit, price analysis, PDF text preview

📊 **Real KPIs**
Dashboard shows invoices processed, vendors, totals, approval rates

🔐 **Compliance Ready**
Audit trails, decision justification, ITC eligibility tracking

💾 **Fallback Mechanism**
Known sample data fills missing fields (with orange banner notification)

🚫 **Duplicate Protection**
File hash + invoice key + exact match detection

📈 **Price Intelligence**
Baseline tracking, variance flagging, spike detection (>20%, >10%, <-10%)

---

## 🛠️ Known Limitations & Roadmap

**Current Limitations:**
- ⏳ Scanned PDFs not supported (need OCR with Tesseract)
- ⏳ Data is in-memory only (resets on server restart)
- ⏳ Vendor master & HSN map are hardcoded JSON
- ⏳ No database persistence
- ⏳ No email notifications on approval decisions

**Planned Features:**
- ✅ Google Sheets integration (live VENDOR_MASTER + PO_DATABASE)
- ✅ SAP connector for live data sync
- ✅ Tesseract OCR for scanned/image invoices
- ✅ PostgreSQL persistence layer
- ✅ Approval workflow emails
- ✅ Mobile app (React Native)
- ✅ VPS deployment (Hostinger 187.53.139.17)
- ✅ Role-based access control (RBAC)

---

## 🧪 Testing

**Sample PDFs Included:**
5 downloadable test invoices covering:
- Normal invoice (auto-approve scenario)
- High-value invoice (plant head review)
- Blacklisted vendor (auto-reject)
- Price spike (finance manager review)
- Duplicate PO (auto-reject)

**Testing Workflow:**
1. Start backend & frontend
2. Go to Upload tab
3. Drag-drop sample PDF
4. Watch 10 agents animate in real-time
5. Review results with full transparency
6. Check History tab for all decisions

---

## 📞 Support & Contact

**Built by:** Sudhan (Hariharasudhan M M)
**Role:** Assistant Manager, Finance | Rane (Madras) Limited, Plant 4
**Course:** Social Eagle AI Batch 11 — GenAI Architect Track

**Questions or Issues?**
- Check the transcript logs in `/mnt/transcripts/`
- Review agent findings in the Results tab
- Inspect PDF text extraction in the PDF preview

**For Production Deployment:**
Contact for Google Sheets integration, SAP connector setup, and VPS configuration.

---

## 📄 License

MIT License — Open for portfolio, learning, and enterprise deployment.

Built with ❤️ for Rane Plant 4 Finance Team.

---

## 🌟 Live Demo

**Dashboard:**
![Dashboard KPIs with real invoice data]

**Upload Interface:**
![Drag-drop PDF upload with file validation]

**Pipeline Animation:**
![10 agents executing in parallel with staggered timing]

**Results Panel:**
![Expandable decision details, agent report, price analysis, PDF text preview]

---

**Ready to deploy?** Start the backend and frontend servers and begin validating invoices in ~1.4 seconds! 🚀