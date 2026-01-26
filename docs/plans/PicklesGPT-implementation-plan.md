# PicklesGPT Implementation Plan

> **Created:** January 26, 2026  
> **Status:** 🚧 PLANNING  
> **Priority:** HIGH  
> **Estimated Timeline:** 6-8 weeks  
> **Monthly Cost:** ~$100-140 on Akash

---

## Overview

**PicklesGPT** (Robo-Pickles) is a financial AI assistant integrated into Trinity that combines:
- RAG across 70+ trading/finance books from `/Documents/The_Library`
- Real-time market data (stocks, crypto, news, economic calendar)
- Authentic Pickles persona with CAPITALIZED terminology
- Automated daily market reports
- All running on Akash backend with GPU acceleration

---

## Architecture Decisions

### Vector Database: **ChromaDB**

| Option | Decision | Reasoning |
|--------|----------|-----------|
| ChromaDB | ✅ **CHOSEN** | Single container, Python-native, perfect for book-scale |
| Qdrant | ❌ | More complex, overkill for this use case |
| Milvus | ❌ | Requires multiple services, enterprise-focused |
| Weaviate | ❌ | Heavier resource requirements |

### Embedding Model: **all-MiniLM-L6-v2**

| Option | Decision | Reasoning |
|--------|----------|-----------|
| all-MiniLM-L6-v2 | ✅ **CHOSEN** | 22MB, 18k sent/sec, CPU-only, excellent quality |
| all-mpnet-base-v2 | ❌ | 420MB, 4x slower, marginal quality gain |
| OpenAI ada-002 | ❌ | Requires API calls, not decentralized |

### Market Data: **Multi-Source Free Stack**

| Data Type | Provider | Decision |
|-----------|----------|----------|
| Stocks | yfinance | ✅ **PRIMARY** - Unlimited, free, reliable |
| Crypto | CoinGecko | ✅ **PRIMARY** - 30 req/min free tier |
| News | Finnhub | ✅ **PRIMARY** - 60 req/min free tier |
| Economic Calendar | Finnhub + RSS | ✅ Combined approach |
| Technicals | Alpha Vantage | ✅ **BACKUP** - 25 req/day free |

### PDF Processing: **PyMuPDF + LangChain**

| Option | Decision | Reasoning |
|--------|----------|-----------|
| PyMuPDF (fitz) | ✅ **CHOSEN** | Fast, handles complex PDFs, preserves structure |
| pdfplumber | ❌ | Slower, issues with some PDF formats |
| PyPDF2 | ❌ | Poor text extraction quality |

---

## Book Library Details

**Location:** `/Documents/The_Library/*.pdf`

### Chunking Strategy

```python
CHUNK_CONFIG = {
    'chunk_size': 512,          # ~100-150 words per chunk
    'chunk_overlap': 50,        # Maintain context between chunks
    'min_chunk_size': 100,      # Skip tiny fragments
    'separators': [
        '\n\n',                 # Paragraph breaks (highest priority)
        '\n',                   # Line breaks
        '. ',                   # Sentences
        ' ',                    # Words (last resort)
    ]
}
```

### Metadata per Chunk

```python
{
    'book_title': 'Trading in the Zone',
    'author': 'Mark Douglas',
    'chapter': 'Chapter 5: The Dynamics of Perception',
    'page_number': 87,
    'topic_tags': ['psychology', 'discipline', 'mindset'],
    'chunk_index': 234,
    'source_file': 'trading_in_the_zone.pdf'
}
```

### Estimated Storage

| Component | Size |
|-----------|------|
| Raw PDF files (~100 books) | ~500 MB - 1 GB |
| Extracted text | ~50-100 MB |
| Embeddings (384-dim vectors) | ~1.5 GB |
| ChromaDB index overhead | ~500 MB |
| **Total** | **~3-4 GB** |

---

## Implementation Phases

### Phase 1: PDF Ingestion Pipeline (Week 1-2)

**Goal:** Extract text from all PDFs and create chunked embeddings

**Tasks:**
- [ ] Add PyMuPDF and sentence-transformers to requirements.txt
- [ ] Create `pickles/ingest_books.py` script
- [ ] Implement PDF text extraction with metadata
- [ ] Implement semantic chunking (by paragraphs/sections)
- [ ] Add ChromaDB to Docker image
- [ ] Create book ingestion endpoint `/pickles/ingest`
- [ ] Test with 5-10 books first, then full library

**Files to Create:**
```
backend/
├── pickles/
│   ├── __init__.py
│   ├── ingest_books.py      # PDF processing + embedding
│   ├── vector_store.py      # ChromaDB interface
│   ├── market_data.py       # Real-time data fetching
│   ├── tools.py             # LLM tool definitions
│   └── persona.py           # System prompts + few-shot
```

**Dependencies to Add:**
```txt
# requirements.txt additions
chromadb>=0.4.0
sentence-transformers>=2.2.0
PyMuPDF>=1.23.0
yfinance>=0.2.0
feedparser>=6.0.0
```

---

### Phase 2: Market Data Integration (Week 3-4)

**Goal:** Real-time stock, crypto, and news data

**Tasks:**
- [ ] Implement yfinance wrapper with caching
- [ ] Implement CoinGecko crypto fetcher
- [ ] Implement Finnhub news integration
- [ ] Create economic calendar parser (RSS + Finnhub)
- [ ] Build caching layer (5-60 second TTLs)
- [ ] Add rate limiting to respect API limits
- [ ] Create `/pickles/market` endpoint for testing

**API Keys Needed:**
```bash
# Add to Akash deployment env
FINNHUB_API_KEY=your_key_here      # Free: finnhub.io
ALPHA_VANTAGE_KEY=your_key_here    # Free: alphavantage.co (optional)
```

**Caching Strategy:**
```python
CACHE_TTL = {
    'quotes': 60,        # 1 minute - stock/crypto prices
    'news': 300,         # 5 minutes - headlines
    'calendar': 3600,    # 1 hour - economic events
    'technicals': 300,   # 5 minutes - indicators
}
```

---

### Phase 3: Tool Calling System (Week 5-6)

**Goal:** Let Pickles decide what data to fetch

**Tasks:**
- [ ] Define tool schemas for Ollama
- [ ] Implement tool execution handlers
- [ ] Create multi-turn conversation flow
- [ ] Add tool result formatting
- [ ] Test tool selection accuracy
- [ ] Create `/pickles/chat` endpoint

**Tool Definitions:**
```python
PICKLES_TOOLS = [
    'get_stock_quote',        # Real-time price + metrics
    'get_crypto_price',       # Crypto prices from CoinGecko
    'search_trading_books',   # RAG against book library
    'get_market_news',        # Latest headlines
    'get_economic_calendar',  # Upcoming data releases
    'get_technical_analysis', # RSI, MACD, moving averages
]
```

**Tool Calling Flow:**
```
1. User asks question
2. Pickles (LLM) decides which tools to call
3. Backend executes tools, returns data
4. Pickles (LLM) responds using real data
```

---

### Phase 4: Persona Engineering (Week 6-7)

**Goal:** Make Pickles authentic and consistent

**Tasks:**
- [ ] Create comprehensive system prompt
- [ ] Add few-shot examples (5-10)
- [ ] Implement CAPITALIZATION enforcement
- [ ] Add price hallucination safeguards
- [ ] Test persona consistency across queries
- [ ] Add disclaimer injection

**CAPITALIZATION Style:**
```
SUPPORT, RESISTANCE, BREAKOUT, BREAKDOWN
VOLUME, PRICE ACTION, MOMENTUM
STOP LOSS, TAKE PROFIT, RISK/REWARD
TREND, REVERSAL, CONSOLIDATION
ENTRY, EXIT, THESIS, SETUP
```

**Holy Gospel (Core Philosophy):**
1. "Wait for your A+ SETUPS"
2. "Trade the CHART, not the BIAS"
3. "Always take PROFITS off the table"

---

### Phase 5: Daily Reports (Week 7-8)

**Goal:** Automated morning briefs and weekly previews

**Tasks:**
- [ ] Create report generation script
- [ ] Set up cron in Docker
- [ ] Design report templates
- [ ] Implement report storage
- [ ] Add report retrieval endpoint `/pickles/reports`
- [ ] Test scheduling

**Report Schedule:**
| Report | Time | Frequency |
|--------|------|-----------|
| Morning Brief | 6:00 AM ET | Mon-Fri |
| Weekly Preview | 6:00 PM ET | Sunday |

**Morning Brief Sections:**
1. OVERNIGHT ACTION (futures moves)
2. KEY LEVELS TO WATCH (S/R for ES, NQ)
3. ECONOMIC EVENTS TODAY
4. EARNINGS REPORTS
5. PICKLES' TAKE (AI commentary)

---

### Phase 6: Frontend Integration (Week 8)

**Goal:** Seamless Trinity UI integration

**Tasks:**
- [ ] Add Pickles mode indicator in chat
- [ ] Show tool usage in responses
- [ ] Add report viewing UI
- [ ] Implement book search UI
- [ ] Add market data widgets (optional)
- [ ] Test end-to-end flow

**UI Changes:**
- Persona dropdown already exists (Trinity/Pickles)
- When Pickles selected, route to `/pickles/chat`
- Show "📊 Fetching market data..." during tool calls
- Display disclaimer at start of Pickles sessions

---

## Akash Deployment

### Updated YAML

```yaml
# deploy-pickles.yaml
version: "2.0"

services:
  trinity-pickles:
    image: gdubx/trinity-pickles:latest
    env:
      - PROVIDER_ID=trinity-pickles
      - MODEL_NAME=llama3.1:8b
      - ENABLE_PICKLES=true
      - CHROMA_PERSIST_DIR=/data/chroma
      - FINNHUB_API_KEY=${FINNHUB_API_KEY}
      - LIGHTHOUSE_API_KEY=${LIGHTHOUSE_API_KEY}
    expose:
      - port: 8000
        as: 80
        to:
          - global: true

profiles:
  compute:
    trinity-pickles:
      resources:
        cpu:
          units: 8
        memory:
          size: 32Gi
        storage:
          size: 150Gi
        gpu:
          units: 1
          attributes:
            vendor:
              nvidia:
                - model: rtx3090
                - model: rtx4090
                - model: a10
```

### Resource Breakdown

| Component | CPU | RAM | Storage |
|-----------|-----|-----|---------|
| Ollama (Llama 3.1 8B) | 4 | 16 GB | 20 GB |
| ChromaDB | 2 | 4 GB | 10 GB |
| Embedding Model | 1 | 1 GB | 100 MB |
| Flask + Services | 1 | 4 GB | 5 GB |
| Books + Cache | - | 2 GB | 10 GB |
| **Total** | **8** | **32 GB** | **~50 GB** |

### Estimated Monthly Cost: **$100-140**

---

## File Structure

```
backend/
├── inference_server.py      # Existing - add Pickles routes
├── pickles/
│   ├── __init__.py
│   ├── ingest_books.py      # PDF → chunks → embeddings
│   ├── vector_store.py      # ChromaDB operations
│   ├── market_data.py       # yfinance, CoinGecko, Finnhub
│   ├── tools.py             # Tool definitions + handlers
│   ├── persona.py           # System prompt + few-shot
│   ├── reports.py           # Daily report generation
│   └── chat.py              # Main Pickles chat handler

trinity-icp/src/
├── tools.js                 # Update Pickles routing
└── pickles/
    └── reports.js           # Report viewing UI (optional)
```

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/pickles/chat` | POST | Main Pickles conversation |
| `/pickles/ingest` | POST | Trigger book ingestion |
| `/pickles/search` | POST | Direct book search |
| `/pickles/market` | GET | Market snapshot |
| `/pickles/reports` | GET | List available reports |
| `/pickles/reports/:date` | GET | Get specific report |
| `/pickles/status` | GET | Pickles system status |

---

## Testing Plan

### Phase 1 Tests
- [ ] PDF extraction accuracy (check 10 random pages)
- [ ] Chunking quality (no broken sentences)
- [ ] Embedding generation (correct dimensions)
- [ ] ChromaDB query accuracy

### Phase 2 Tests
- [ ] yfinance quote accuracy
- [ ] CoinGecko price accuracy
- [ ] News freshness (< 1 hour old)
- [ ] Rate limiting works

### Phase 3 Tests
- [ ] Tool selection accuracy (correct tool for question)
- [ ] Multi-tool queries work
- [ ] Graceful fallback on tool failure

### Phase 4 Tests
- [ ] Persona consistency (CAPITALIZATION)
- [ ] No price hallucinations
- [ ] Philosophy alignment ("Wait for A+ SETUPS")

### Phase 5 Tests
- [ ] Reports generate on schedule
- [ ] Report content is accurate
- [ ] Reports are retrievable

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| PDF extraction fails | Fallback to OCR, manual review of problem PDFs |
| API rate limits | Aggressive caching, multiple providers |
| Tool calling errors | Graceful fallback to general response |
| Price hallucinations | Strict "never guess" prompt rules |
| ChromaDB cold start | Warm-up on container start |

---

## Success Criteria

1. **RAG Quality:** >80% relevant results on book queries
2. **Market Data Latency:** <2 seconds for quotes
3. **Persona Consistency:** CAPITALIZATION in >90% of responses
4. **Report Reliability:** 95% on-time generation
5. **User Satisfaction:** Feels like talking to a real trader

---

## Next Steps

1. **Immediate:** Copy books from `/Documents/The_Library` to Trinity workspace
2. **Week 1:** Start Phase 1 - PDF ingestion pipeline
3. **Get API Keys:** Register for Finnhub (free) at finnhub.io

---

## References

- ChromaDB Docs: https://docs.trychroma.com/
- Sentence Transformers: https://www.sbert.net/
- Finnhub API: https://finnhub.io/docs/api
- yfinance: https://github.com/ranaroussi/yfinance
- Ollama Tool Calling: https://ollama.com/blog/tool-support
