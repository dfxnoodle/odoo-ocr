# EIR OCR Platform

A web platform that extracts structured data from Equipment Interchange Receipt (EIR) documents using Google Vertex AI Gemini, presents a human-in-the-loop validation UI, and commits verified records directly to Odoo via XML-RPC.

---

## Architecture

```
┌─────────────┐   upload   ┌──────────────────────────────────────────┐
│ Vue 3 / Vite│ ─────────► │  FastAPI Backend                          │
│  Frontend   │ ◄───────── │  /api/v1/extract                          │
│             │   JSON     │  /api/v1/odoo/commit                      │
│  Split-pane │            │  /api/v1/health                           │
│  Validation │            │                                           │
│  UI         │            │  ExtractionProviderFactory                │
└──────┬──────┘            │  ├── VertexGeminiExtractor (default)      │
       │ confirm           │  ├── AzureDocIntelExtractor (stub)        │
       ▼                   │  └── PaddleCpuExtractor (stub)            │
┌─────────────┐            │                                           │
│   Odoo ERP  │ ◄───────── │  EIRToOdooMapper → OdooXmlRpcClient      │
└─────────────┘  xmlrpc    └──────────────────────────────────────────┘
```

---

## Quick Start (Development)

### Prerequisites
- Python 3.14 ([download](https://www.python.org/downloads/) or `sudo apt install python3.14 python3.14-venv`)
- Node.js 22+
- A GCP project with Vertex AI enabled and a service account key

### One-command start

```bash
# First-time setup: creates venv, installs all dependencies, copies .env
./dev.sh setup

# Edit backend/.env with your VERTEX_PROJECT_ID and ODOO_* credentials, then:
./dev.sh          # starts backend + frontend together
```

| Command | What it does |
|---|---|
| `./dev.sh setup` | Creates venv, installs Python + Node deps, copies `.env.example` → `backend/.env` |
| `./dev.sh` or `./dev.sh both` | Starts FastAPI backend + Vite frontend side-by-side |
| `./dev.sh backend` | Starts only the FastAPI backend (port 8000) |
| `./dev.sh frontend` | Starts only the Vite dev server (port 5173) |
| `./dev.sh test` | Runs the full pytest suite |

- Backend API docs: http://localhost:8000/api/docs
- Frontend: http://localhost:5173 (proxies `/api/*` to port 8000)

### Manual setup (optional)

```bash
cd backend
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env   # then edit .env
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

### Run Tests

```bash
./dev.sh test
# or directly:
cd backend && pytest -v --tb=short
```

---

## Configuration Reference

Copy `.env.example` to `backend/.env` and fill in the values.

| Variable | Default | Description |
|---|---|---|
| `EXTRACTION_PROVIDER` | `vertex` | `vertex` \| `azure` \| `paddle` |
| `VERTEX_PROJECT_ID` | — | GCP project ID |
| `VERTEX_LOCATION` | `us-central1` | Vertex AI region |
| `VERTEX_MODEL` | `gemini-2.0-flash-001` | Gemini model name |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Path to GCP service account JSON |
| `AZURE_DOCINTEL_ENDPOINT` | — | Azure Document Intelligence endpoint |
| `AZURE_DOCINTEL_KEY` | — | Azure Document Intelligence API key |
| `ODOO_URL` | — | Odoo instance base URL |
| `ODOO_DB` | — | Odoo database name |
| `ODOO_USERNAME` | — | Odoo API user email |
| `ODOO_PASSWORD` | — | Odoo API key or password |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |

---

## Production Deployment

### Docker (single container)

```bash
# Build
docker build -t eir-ocr-platform:latest .

# Run
docker run -p 8000:8000 --env-file .env eir-ocr-platform:latest
```

### Docker Compose

```bash
cp .env.example .env   # fill in secrets
docker compose up -d
```

### Azure Container Apps

1. Push the image to Azure Container Registry (ACR):
   ```bash
   az acr build --registry <ACR_NAME> --image eir-ocr-platform:latest .
   ```
2. Edit `infra/aca/containerapp.yaml` — replace all `<PLACEHOLDER>` values.
3. Deploy:
   ```bash
   az containerapp create \
     --resource-group <RG> \
     --environment <ACA_ENV> \
     --yaml infra/aca/containerapp.yaml
   ```

### Azure App Service

```bash
az deployment group create \
  --resource-group <RG> \
  --template-file infra/appservice/appservice.bicep \
  --parameters acrLoginServer=<ACR>.azurecr.io \
               acrUsername=<ACR_USER> \
               acrPassword=<ACR_PASS> \
               odooUrl=https://... \
               odooDb=... \
               odooUsername=... \
               odooPassword=... \
               vertexProjectId=...
```

---

## Odoo Custom Fields

The mapper targets `stock.picking` with these custom fields (prefix `x_`).
Create them in Odoo Settings → Technical → Custom Fields, or via a custom module:

| Field name | Type | Description |
|---|---|---|
| `x_container_number` | Char | ISO 6346 container ID |
| `x_seal_number` | Char | Seal number |
| `x_container_size` | Char | e.g. 40, 40HC |
| `x_container_type` | Char | e.g. GP, RF |
| `x_condition` | Char | e.g. CLEAN, DAMAGED |
| `x_vessel_name` | Char | Vessel name |
| `x_voyage_number` | Char | Voyage number |
| `x_bill_of_lading` | Char | B/L reference |
| `x_booking_number` | Char | Booking reference |
| `x_port_of_loading` | Char | Port of loading (UN/LOCODE) |
| `x_port_of_discharge` | Char | Port of discharge (UN/LOCODE) |
| `x_commodity` | Char | Cargo description |
| `x_gross_weight` | Float | Gross weight in KG |
| `x_net_weight` | Float | Net weight in KG |
| `x_tare_weight` | Float | Tare weight in KG |
| `x_shipping_line_id` | Many2one → res.partner | Shipping line partner |

---

## Project Structure

```
odoo-ocr/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI application entry point
│   │   ├── core/
│   │   │   ├── config.py         Pydantic settings (reads .env)
│   │   │   └── logging.py        Structured logging (structlog)
│   │   ├── api/v1/
│   │   │   ├── extract.py        POST /api/v1/extract
│   │   │   ├── odoo.py           POST /api/v1/odoo/commit
│   │   │   └── health.py         GET  /api/v1/health
│   │   ├── schemas/
│   │   │   └── extraction.py     Pydantic models for all I/O
│   │   └── services/
│   │       ├── extractors/
│   │       │   ├── base.py       Abstract extractor + factory
│   │       │   ├── vertex_gemini.py  Default provider
│   │       │   ├── azure_docintel.py Stub
│   │       │   └── paddle_cpu.py     Stub
│   │       └── odoo/
│   │           └── client.py     XML-RPC client + field mapper
│   ├── tests/                    pytest test suite
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.vue               Shell with header + router-view
│   │   ├── main.ts               App entry (Pinia + Router)
│   │   ├── components/
│   │   │   ├── DocumentUploader.vue  Drag-and-drop uploader
│   │   │   └── ValidationView.vue    Split-pane review form
│   │   ├── composables/
│   │   │   ├── useExtract.ts     Extract API call wrapper
│   │   │   └── useCommit.ts      Commit API call wrapper
│   │   ├── stores/
│   │   │   └── extraction.ts     Pinia state for the session
│   │   ├── types/
│   │   │   └── extraction.ts     TypeScript types mirroring schema
│   │   └── views/
│   │       ├── UploadView.vue
│   │       ├── ValidateView.vue
│   │       └── CommittedView.vue
│   ├── package.json
│   └── vite.config.ts            Builds into backend/static/
├── infra/
│   ├── aca/containerapp.yaml     Azure Container Apps manifest
│   └── appservice/appservice.bicep  Azure App Service Bicep template
├── Dockerfile                    Multi-stage build
├── docker-compose.yml
├── .env.example
└── README.md
```
