# VIVAYU Aqua

VIVAYU Aqua is a two-zone, scarcity-aware irrigation intelligence platform for
InnoHack 2.0. It combines field sensing, crop configuration, weather,
freshwater availability, and irrigation-water TDS to choose and verify a water
strategy before irrigation.

The project is intentionally being built milestone-by-milestone. The legacy
Vivayu model remains a research-only plant/VOC monitoring signal and will never
directly trigger irrigation.

## Repository layout

- `backend/` — FastAPI API, domain services, persistence, and tests
- `frontend/` — Next.js/TypeScript judge-facing dashboard
- `firmware/` — ESP32 field-node and controller firmware
- `legacy/vivayu/` — pinned upstream Vivayu research snapshot
- `docs/` — master specification, status, contracts, decisions, and runbook
- `runtime/` — ignored local database and logs

## Development setup

Simulation is the default data mode so the application can run without
connected hardware.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:3000`. The backend health endpoint is available at
`http://localhost:8000/api/v1/health`.

Before implementing a milestone, read `docs/CODEX_MASTER_REFERENCE.md` and
`AGENTS.md`.
