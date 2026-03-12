# APIS v5.0 — Autonomous Pothole Intelligence System

## Production System for CHIPS AIML Hackathon PS-02

### 🛰️ Real Data Sources
- **Sentinel-2** optical satellite imagery (10m resolution, 5-day cycle)
- **Sentinel-1** SAR for monsoon fallback + InSAR subsidence prediction
- **NHAI ATMS** live CCTV (60-80 cameras on NH-30)
- **Mobile App** accelerometer + camera reports from citizens

### 🤖 AI Pipeline
- **YOLOv8x-seg** pothole detection (trained on RDD2022 + India datasets)
- **MiDaS v3** depth estimation (cm-calibrated for NH-30)
- **Gemini 1.5 Pro** formal complaint letter generation
- **XGBoost** predictive pothole emergence from SAR subsidence

### 📊 Features
- Multi-factor risk scoring (0-10 scale, 9 factors)
- Automated PG Portal grievance filing (Selenium + 2captcha)
- Three-tier auto-escalation (Division → Regional → NHAI HQ + RTI)
- SSIM-based repair verification (ORB alignment + region focus)
- Citizen WhatsApp verification polls (Twilio)
- Real-time weather integration (Open-Meteo API)

### 🏗️ Architecture
```
├── backend/              # FastAPI + Python services
│   ├── app/
│   │   ├── api/          # REST API routers
│   │   ├── models/       # SQLAlchemy ORM (PostGIS)
│   │   ├── schemas/      # Pydantic models
│   │   ├── services/     # Business logic
│   │   │   └── detection/  # Satellite, CCTV, YOLO, depth
│   │   └── tasks/        # Celery async workers
│   └── dags/             # Airflow DAG definitions
├── dashboard/            # React + Mapbox GL SPA
├── schema/               # PostgreSQL + PostGIS DDL
└── README.md
```

### 🚀 Quick Start

**Backend:**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env    # fill in credentials
uvicorn app.main:app --reload --port 8000
```

**Dashboard:**
```bash
cd dashboard
npm install
npm run dev
```

### 📋 API Endpoints
| Endpoint | Description |
|---|---|
| `GET /api/potholes` | List with filters (highway, severity, bbox) |
| `GET /api/potholes/geojson` | GeoJSON for map rendering |
| `GET /api/potholes/{uuid}` | Full pothole passport |
| `GET /api/potholes/{uuid}/timeline` | Lifecycle event timeline |
| `POST /api/reports/mobile` | Mobile report ingestion |
| `GET /api/complaints` | Complaint list + escalation log |
| `GET /api/stretches` | Highway risk analysis |
| `GET /api/analytics/summary` | Dashboard KPIs |
| `GET /api/predict` | SAR-predicted potholes |

### 🌐 Live Region
- NH-30 Raipur–Bilaspur corridor (~120 km)
- NH-53 Raipur–Jagdalpur (~300 km)
- NH-130C Raipur–Ambikapur

### 📄 License
CHIPS AIML Hackathon PS-02 — Chhattisgarh Infotech Promotion Society
