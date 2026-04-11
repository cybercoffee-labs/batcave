# BATMAN LAB — GOOGLE CLOUD SPEC v1.0
# Upgrade Plan Using $300 Free Credit + Always Free Tier
# Date: 2026-03-17
#
# From 200+ Google APIs, ONLY these 18 matter for Batman Lab + your projects.
# Organized by: what it does for YOU, cost, and priority.

---

## 0. WHAT YOU GET FREE

**$300 credit** — expires in 90 days. Use it for compute-heavy stuff.
**Always Free tier** — NEVER expires. Use it for everything else.

Always Free limits that matter to us:
- Cloud Run: 2M requests/month (Batman 24/7 = ~130K requests/month — FITS)
- BigQuery: 1TB queries/month + 10GB storage (Batman signals = ~50MB — FITS)
- Pub/Sub: 10GB messages/month (alerts = ~1MB — FITS)
- Cloud Functions: 2M invocations/month
- Cloud Scheduler: 3 jobs free
- Secret Manager: 6 secrets + 10K accesses/month
- Firestore: 1GB storage + 50K reads/day
- Cloud Build: 120 build-min/day
- Cloud Logging: 50GB/month
- Cloud Monitoring: free for GCP metrics
- Vision AI: 1,000 units/month
- Natural Language API: 5,000 units/month
- Cloud Shell: free terminal + 5GB persistent storage

---

## 1. BATMAN LAB — CORE INFRASTRUCTURE (Priority: NOW)

### 1.1 Cloud Run — Batman 24/7 ($0.00)
**What:** Run Batman engine in the cloud. Scans 8 markets every 20 min. Never stops.
**Why:** Your Mac Mini sleeps = Batman dies. Cloud Run = Batman never dies.
**Free tier:** 2M requests/month, 180K vCPU-seconds, 360K GiB-seconds
**Batman uses:** ~6,480 requests/month (3 per hour × 24h × 30 days × 3 scanners) = WAY under limit
**Setup:** Containerize batman_flow_engine with Docker, deploy to Cloud Run
**API:** run.googleapis.com

### 1.2 Cloud Scheduler — Automatic Cron ($0.00)
**What:** Triggers Batman every 20 minutes automatically.
**Why:** Replaces run_loop.py. No terminal needed.
**Free tier:** 3 jobs free/month
**Batman uses:** 1 job (every 20 min) = FITS
**API:** cloudscheduler.googleapis.com

### 1.3 Pub/Sub — Real-time Alerts ($0.00)
**What:** Batman detects opportunity → Pub/Sub → triggers alert function
**Why:** Instant notification pipeline. Decouples detection from alerting.
**Free tier:** 10GB messages/month
**Batman uses:** ~1MB/month max = FITS
**API:** pubsub.googleapis.com

### 1.4 Cloud Functions — Alert Dispatcher ($0.00)
**What:** Receives Pub/Sub message, sends Telegram/email/WhatsApp alert
**Why:** You get notified on your phone INSTANTLY when Batman finds opportunity
**Free tier:** 2M invocations/month
**Batman uses:** ~200/month max = FITS
**API:** cloudfunctions.googleapis.com

### 1.5 BigQuery — Analytics at Scale ($0.00)
**What:** All Batman signals + opportunities go to BigQuery
**Why:** SQL queries on ALL historical data. "Show me all MXN opportunities > 1% edge in March" = 2 seconds
**Free tier:** 1TB queries/month + 10GB storage
**Batman uses:** ~50MB storage, ~1GB queries = FITS
**API:** bigquery.googleapis.com

### 1.6 Secret Manager — Secure API Keys ($0.00)
**What:** Store Binance/OKX/Bybit API keys encrypted
**Why:** No more .env files with plaintext keys. Professional security.
**Free tier:** 6 secrets + 10K accesses/month
**Batman uses:** 5 secrets (one per exchange) = FITS
**API:** secretmanager.googleapis.com

### 1.7 Cloud Storage — Data Backup ($0.00)
**What:** Backup opportunities.jsonl, batman.db, trades.jsonl to cloud
**Why:** Mac Mini dies = you lose 2 weeks of data. Cloud Storage = safe forever.
**Free tier:** 5GB/month
**Batman uses:** ~100MB = FITS
**API:** storage.googleapis.com

---

## 2. BATMAN LAB — INTELLIGENCE UPGRADE (Priority: THIS WEEK)

### 2.1 Vertex AI / Gemini API — Upgrade BARBARA ($300 credit)
**What:** Replace Ollama llama3.2:3b with Gemini Pro for opportunity analysis
**Why:** 100x better reasoning. Can analyze complex cross-currency opportunities.
**Cost:** ~$0.001 per analysis with Gemini Flash, ~$0.01 with Gemini Pro
**Budget:** $5/month = 5,000 analyses = MORE than enough
**Free tier:** Gemini has free tier for many models
**API:** aiplatform.googleapis.com

### 2.2 Natural Language API — News Sentiment ($0.00)
**What:** Analyze news articles for market sentiment (BARBARA enhancement)
**Why:** "Argentina announces new currency controls" → BARBARA says ARS premium will increase
**Free tier:** 5,000 units/month = 5,000 news articles analyzed
**API:** language.googleapis.com

### 2.3 Cloud Firestore — Live Dashboard Database ($0.00)
**What:** Real-time database for live dashboard
**Why:** Store current market state, opportunities, P&L. Dashboard reads in real-time.
**Free tier:** 1GB + 50K reads/day
**API:** firestore.googleapis.com

---

## 3. MONITORING & OPERATIONS (Priority: THIS WEEK)

### 3.1 Google Sheets API — Mobile Dashboard ($0.00)
**What:** Batman writes opportunities to a Google Sheet automatically
**Why:** Open Sheet on your phone = see all 8 scanners in real-time. No terminal.
**Free tier:** Completely free with Google Workspace
**API:** sheets.googleapis.com

### 3.2 Gmail API — Email Alerts ($0.00)
**What:** Send yourself email alerts when high-value opportunities appear
**Why:** Backup alert channel. Telegram + Email = never miss an opportunity.
**Free tier:** Free with your Gmail
**API:** gmail.googleapis.com

### 3.3 Cloud Monitoring + Logging ($0.00)
**What:** Monitor Batman health, uptime, errors. Dashboards in Google Cloud Console.
**Why:** Professional operations. Know when Batman is down before you lose money.
**Free tier:** 50GB logs/month + free GCP metrics
**API:** monitoring.googleapis.com + logging.googleapis.com

---

## 4. FOTOGENIO / VKPF (Priority: NEXT MONTH)

### 4.1 Vision AI — Image Analysis ($0.00)
**What:** Analyze poster designs, detect quality issues, classify content
**Why:** VKPF quality control. Auto-detect bad compositions before publishing.
**Free tier:** 1,000 units/month
**API:** vision.googleapis.com

### 4.2 YouTube Data API — Content Distribution ($0.00)
**What:** Auto-publish VKPF content to YouTube, analyze performance
**Why:** VKPF distribution channel. Track which content performs best.
**Free tier:** 10,000 units/day
**API:** youtube.googleapis.com

### 4.3 Analytics API — Traffic Tracking ($0.00)
**What:** Track Fotogenio website/social traffic
**Why:** Measure what content drives sales
**Free tier:** Completely free
**API:** analyticsdata.googleapis.com

---

## 5. SUPER AGENTE CONTABLE (Priority: NEXT MONTH)

### 5.1 Document AI — CFDI/PDF Processing ($300 credit)
**What:** Extract data from SAT CFDIs, BBVA statements, invoices
**Why:** Automate your contable workflow. Read 1000 CFDIs in seconds.
**Cost:** ~$0.01 per page processed
**Budget:** $10/month = 1,000 pages
**API:** documentai.googleapis.com

---

## 6. WHAT YOU DON'T NEED (SKIP THESE)

| API Category | Why Skip |
|-------------|----------|
| Maps (32 APIs) | Not relevant to arbitrage or content |
| Healthcare (1) | Not your domain |
| Retail (1) | Fotogenio is too small for enterprise retail APIs |
| Mobile (12) | No mobile app planned |
| DevOps (25) | Overkill — Cloud Run + Functions is enough |
| Networking (8) | Not managing network infrastructure |
| Enterprise (182) | Corporate APIs for Fortune 500, not solo operators |
| Sustainability (4) | Not relevant |
| Operating Systems (1) | Not managing OS fleet |
| Advertising (14) | Use direct affiliate links, not ad APIs |
| Social (4) | Direct posting is better than API for your scale |
| Media (1) | Not a media company |

---

## 7. COST BREAKDOWN — 90 DAY PLAN

### Month 1 (from $300 credit):
| Service | Cost | What |
|---------|------|------|
| Cloud Run | $0.00 | Batman 24/7 |
| Cloud Scheduler | $0.00 | Auto-trigger |
| Pub/Sub | $0.00 | Alert pipeline |
| Cloud Functions | $0.00 | Alert dispatch |
| BigQuery | $0.00 | Analytics |
| Secret Manager | $0.00 | API keys |
| Sheets API | $0.00 | Mobile dashboard |
| Vertex AI (Gemini) | ~$5.00 | BARBARA upgrade |
| **TOTAL** | **~$5.00** | **From $300 credit** |

### Month 2:
| Service | Cost |
|---------|------|
| Same as Month 1 | ~$5.00 |
| Document AI | ~$10.00 |
| **TOTAL** | **~$15.00** |

### Month 3:
| Service | Cost |
|---------|------|
| Same as above | ~$15.00 |
| Vision AI (VKPF) | $0.00 (free tier) |
| **TOTAL** | **~$15.00** |

### 90-Day Total: ~$35 of $300 credit used. $265 remaining.

---

## 8. IMPLEMENTATION ORDER FOR CLAUDE CODE

**Day 1 (Tomorrow):**
1. Create Dockerfile for batman_flow_engine
2. Deploy to Cloud Run
3. Set up Cloud Scheduler (every 20 min)
4. Connect Pub/Sub for alerts
5. Create Cloud Function → Telegram alert

**Day 2:**
6. Set up BigQuery dataset + tables
7. Modify Batman to write to BigQuery (in addition to local JSONL)
8. Set up Google Sheets auto-update
9. Configure Secret Manager for API keys

**Day 3:**
10. Integrate Vertex AI / Gemini for BARBARA
11. Set up Cloud Monitoring + Logging
12. Test full pipeline: Batman scans → detects → alerts phone

**Week 2:**
13. Document AI for Super Agente Contable
14. Vision AI for VKPF
15. YouTube API for content distribution

---

## 9. APIS TO ENABLE IN GOOGLE CLOUD CONSOLE

Go to console.cloud.google.com → APIs & Services → Enable:

```
run.googleapis.com
cloudscheduler.googleapis.com
pubsub.googleapis.com
cloudfunctions.googleapis.com
bigquery.googleapis.com
secretmanager.googleapis.com
storage.googleapis.com
aiplatform.googleapis.com
language.googleapis.com
firestore.googleapis.com
sheets.googleapis.com
gmail.googleapis.com
monitoring.googleapis.com
logging.googleapis.com
cloudbuild.googleapis.com
```

---

## 10. SECURITY RULES

1. NEVER put GCP service account keys in the repo
2. Use Secret Manager for ALL API keys (Binance, OKX, etc.)
3. Enable billing alerts at $10, $50, $100
4. Restrict Cloud Run to only accept Cloud Scheduler triggers
5. Use IAM with minimum permissions per service

---

*Created: 2026-03-17 | Batman Lab Google Cloud Upgrade*
*Budget: $300 free credit | Estimated 90-day cost: ~$35*
*Result: Batman runs 24/7 in cloud, alerts to phone, analytics at scale*
