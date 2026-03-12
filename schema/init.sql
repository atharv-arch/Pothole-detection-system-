-- ═══════════════════════════════════════════════════════════════
-- APIS v5.0 — Production PostgreSQL Schema (PostGIS)
-- Section 12 of the production specification
-- ═══════════════════════════════════════════════════════════════

-- Enable PostGIS extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- ── Potholes ─────────────────────────────────────────────────
CREATE TABLE potholes (
    uuid                TEXT PRIMARY KEY,
    gps                 GEOGRAPHY(POINT, 4326) NOT NULL,
    highway_id          TEXT NOT NULL,
    km_marker           DECIMAL(6,1),
    district            TEXT,
    lane_position       TEXT CHECK (lane_position IN
                            ('centre','left','right','shoulder')),
    severity            TEXT CHECK (severity IN
                            ('low','medium','high','critical')),
    risk_score          DECIMAL(4,2) CHECK (risk_score BETWEEN 0 AND 10),
    area_sqm            DECIMAL(6,3),
    depth_cm            DECIMAL(5,1),
    status              TEXT NOT NULL DEFAULT 'detected',
    source_primary      TEXT CHECK (source_primary IN
                            ('satellite','cctv','mobile','sar')),
    confidence          DECIMAL(4,3) CHECK (confidence BETWEEN 0 AND 1),
    first_detected      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_scanned        TIMESTAMPTZ,
    weather_at_detection JSONB,
    repair_verified     BOOLEAN DEFAULT FALSE,
    ssim_score          DECIMAL(4,3),
    image_before        TEXT,
    image_after         TEXT,
    yolo_mask_polygon   JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── Complaints ───────────────────────────────────────────────
CREATE TABLE complaints (
    complaint_id        TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    pothole_uuid        TEXT REFERENCES potholes(uuid) ON DELETE CASCADE,
    portal              TEXT NOT NULL,
    filed_at            TIMESTAMPTZ,
    reference_number    TEXT,
    tier                INTEGER DEFAULT 1 CHECK (tier BETWEEN 1 AND 3),
    sla_deadline        TIMESTAMPTZ,
    escalated_at        TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    letter_text         TEXT,
    letter_pdf_s3       TEXT,
    confirmation_s3     TEXT,
    status              TEXT DEFAULT 'pending',
    filing_method       TEXT DEFAULT 'selenium'
);

-- ── Escalation Log ───────────────────────────────────────────
CREATE TABLE escalation_log (
    id                  SERIAL PRIMARY KEY,
    complaint_id        TEXT REFERENCES complaints(complaint_id),
    pothole_uuid        TEXT,
    tier_from           INTEGER,
    tier_to             INTEGER,
    escalated_at        TIMESTAMPTZ DEFAULT NOW(),
    reason              TEXT,
    new_ref_number      TEXT,
    rti_reference       TEXT,
    gemini_letter       TEXT,
    sms_sid             TEXT,
    days_since_original INTEGER
);

-- ── Scan History ─────────────────────────────────────────────
CREATE TABLE scan_history (
    scan_id             SERIAL PRIMARY KEY,
    pothole_uuid        TEXT REFERENCES potholes(uuid),
    scanned_at          TIMESTAMPTZ DEFAULT NOW(),
    source              TEXT,
    confidence          DECIMAL(4,3),
    image_path          TEXT,
    ssim_vs_prev        DECIMAL(4,3),
    diff_map_path       TEXT,
    verdict             TEXT,
    yolo_detected       BOOLEAN
);

-- ── Source Reports (Mobile / CCTV / Satellite) ───────────────
CREATE TABLE source_reports (
    id                  SERIAL PRIMARY KEY,
    source              TEXT,
    gps                 GEOGRAPHY(POINT, 4326),
    highway_id          TEXT,
    km_marker           DECIMAL(6,1),
    jolt_magnitude      DECIMAL(5,3),
    speed_kmh           DECIMAL(5,1),
    device_id           TEXT,
    video_s3_url        TEXT,
    report_type         TEXT,
    processed           BOOLEAN DEFAULT FALSE,
    pothole_uuid        TEXT,
    timestamp           TIMESTAMPTZ DEFAULT NOW()
);

-- ── Citizen Verifications ────────────────────────────────────
CREATE TABLE citizen_verifications (
    id                  SERIAL PRIMARY KEY,
    pothole_uuid        TEXT REFERENCES potholes(uuid),
    phone_hash          TEXT,
    response            TEXT CHECK (response IN ('1','2','3')),
    timestamp           TIMESTAMPTZ DEFAULT NOW()
);

-- ── CCTV Nodes ───────────────────────────────────────────────
CREATE TABLE cctv_nodes (
    camera_id           TEXT PRIMARY KEY,
    gps                 GEOGRAPHY(POINT, 4326),
    highway_id          TEXT,
    km_marker           DECIMAL(6,1),
    rtsp_url            TEXT,
    atms_zone           TEXT,
    is_online           BOOLEAN DEFAULT TRUE,
    last_checked        TIMESTAMPTZ
);

-- ── Highway Segments ─────────────────────────────────────────
CREATE TABLE highway_segments (
    segment_id          SERIAL PRIMARY KEY,
    highway_id          TEXT,
    km_start            DECIMAL(6,1),
    km_end              DECIMAL(6,1),
    road_buffer         GEOGRAPHY(POLYGON, 4326),
    speed_limit_kmh     INTEGER,
    aadt                INTEGER,
    is_curve            BOOLEAN DEFAULT FALSE,
    road_age_years      DECIMAL(4,1),
    district            TEXT,
    night_accident_ratio DECIMAL(4,3)
);

-- ── Accident History ─────────────────────────────────────────
CREATE TABLE accident_history (
    accident_id         SERIAL PRIMARY KEY,
    highway_id          TEXT,
    km_marker           DECIMAL(6,1),
    accident_date       DATE,
    severity            TEXT,
    vehicle_type        TEXT,
    cause               TEXT,
    lat                 DECIMAL(9,6),
    lon                 DECIMAL(9,6)
);

-- ═══════════════════════════════════════════════════════════════
-- Spatial & Performance Indexes
-- ═══════════════════════════════════════════════════════════════
CREATE INDEX idx_potholes_gps
    ON potholes USING GIST (gps);
CREATE INDEX idx_potholes_status_risk
    ON potholes (status, risk_score DESC);
CREATE INDEX idx_potholes_highway
    ON potholes (highway_id, km_marker);
CREATE INDEX idx_source_reports_gps
    ON source_reports USING GIST (gps);
CREATE INDEX idx_source_reports_device
    ON source_reports (device_id, timestamp DESC);
CREATE INDEX idx_highway_segments_buffer
    ON highway_segments USING GIST (road_buffer);
CREATE INDEX idx_complaints_status
    ON complaints (status, sla_deadline);
CREATE INDEX idx_complaints_pothole
    ON complaints (pothole_uuid);
CREATE INDEX idx_scan_history_pothole
    ON scan_history (pothole_uuid, scanned_at DESC);
CREATE INDEX idx_accident_history_highway
    ON accident_history (highway_id, km_marker);
CREATE INDEX idx_citizen_verifications_pothole
    ON citizen_verifications (pothole_uuid);
