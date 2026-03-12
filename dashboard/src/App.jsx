// ═══════════════════════════════════════════════════════════
// APIS v5.0 — Main Dashboard Application
// React SPA with Map, Sidebar, KPIs, Analytics
// ═══════════════════════════════════════════════════════════

import React, { useState, useEffect, useRef, useCallback } from 'react';
import mapboxgl from 'mapbox-gl';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
         XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { MapPin, AlertTriangle, FileText, TrendingUp, Shield, Radio,
         Eye, Layers, Activity, ChevronRight, Clock, Satellite,
         Camera, Smartphone, Zap, Search, Bell } from 'lucide-react';
import { api, SEVERITY_COLORS, STATUS_LABELS, formatDate, formatDateTime, timeAgo } from './utils/api.js';

// Mapbox token — will use env var or demo token
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || 'pk.demo';

// ── Severity color helpers ────────────────────────────────
const riskColor = (score) => {
  if (score >= 8) return 'var(--critical)';
  if (score >= 6) return 'var(--high)';
  if (score >= 4) return 'var(--medium)';
  return 'var(--low)';
};

const severityClass = (sev) => sev || 'medium';

// ── Demo data for rendering without backend ───────────────
const DEMO_POTHOLES = [
  { uuid: 'PTH-20260312-A1B2C3', highway_id: 'NH-30', km_marker: 145.2, severity: 'critical', risk_score: 9.12, status: 'escalated_l2', lat: 21.4821, lon: 81.8432, source_primary: 'satellite', confidence: 0.94, first_detected: '2026-02-28T10:30:00Z', depth_cm: 12.3, area_sqm: 2.45 },
  { uuid: 'PTH-20260310-D4E5F6', highway_id: 'NH-30', km_marker: 152.7, severity: 'high', risk_score: 7.45, status: 'complaint_filed', lat: 21.5234, lon: 81.8901, source_primary: 'cctv', confidence: 0.89, first_detected: '2026-03-02T14:20:00Z', depth_cm: 8.7, area_sqm: 1.32 },
  { uuid: 'PTH-20260309-G7H8I9', highway_id: 'NH-30', km_marker: 138.5, severity: 'medium', risk_score: 5.23, status: 'detected', lat: 21.4512, lon: 81.8123, source_primary: 'mobile', confidence: 0.78, first_detected: '2026-03-05T08:15:00Z', depth_cm: 5.1, area_sqm: 0.67 },
  { uuid: 'PTH-20260308-J1K2L3', highway_id: 'NH-30', km_marker: 167.3, severity: 'critical', risk_score: 8.67, status: 'sla_breach_public', lat: 21.5891, lon: 81.9456, source_primary: 'satellite', confidence: 0.96, first_detected: '2026-02-15T06:00:00Z', depth_cm: 15.2, area_sqm: 3.10 },
  { uuid: 'PTH-20260307-M4N5O6', highway_id: 'NH-53', km_marker: 45.8, severity: 'low', risk_score: 2.89, status: 'verified_repaired', lat: 21.2345, lon: 81.6789, source_primary: 'cctv', confidence: 0.82, first_detected: '2026-02-20T16:45:00Z', depth_cm: 3.2, area_sqm: 0.25 },
  { uuid: 'PRED-20260311-P7Q8R9', highway_id: 'NH-30', km_marker: 155.0, severity: 'high', risk_score: 6.8, status: 'pred_unconfirmed', lat: 21.5456, lon: 81.9012, source_primary: 'sar', confidence: 0.72, first_detected: '2026-03-11T02:00:00Z', depth_cm: 0, area_sqm: 0 },
];

const DEMO_ANALYTICS = {
  total_active: 47, total_repaired: 23, total_complaints_filed: 38, total_sla_breached: 5,
  avg_risk_score: 5.87, detections_last_7d: 12, repairs_verified: 18, highways_monitored: 3,
  severity_distribution: { critical: 8, high: 14, medium: 17, low: 8 },
  source_distribution: { satellite: 22, cctv: 15, mobile: 7, sar: 3 },
  monthly_trend: [
    { month: '2025-10', detected: 15, repaired: 8 },
    { month: '2025-11', detected: 22, repaired: 12 },
    { month: '2025-12', detected: 18, repaired: 14 },
    { month: '2026-01', detected: 25, repaired: 16 },
    { month: '2026-02', detected: 31, repaired: 19 },
    { month: '2026-03', detected: 12, repaired: 4 },
  ],
};


// ═══════════════════════════════════════════════════════════
// Main App Component
// ═══════════════════════════════════════════════════════════
export default function App() {
  const [view, setView] = useState('map');
  const [potholes, setPotholes] = useState(DEMO_POTHOLES);
  const [analytics, setAnalytics] = useState(DEMO_ANALYTICS);
  const [selectedPothole, setSelectedPothole] = useState(null);
  const [mapStyle, setMapStyle] = useState('dark');
  const [showHeatmap, setShowHeatmap] = useState(false);
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);

  // Fetch real data (fallback to demo)
  useEffect(() => {
    (async () => {
      const [realPotholes, realAnalytics] = await Promise.all([
        api.getPotholes('limit=100'),
        api.getAnalyticsSummary(),
      ]);
      if (realPotholes && realPotholes.length > 0) setPotholes(realPotholes);
      if (realAnalytics && realAnalytics.total_active !== undefined) setAnalytics(realAnalytics);
    })();
  }, []);

  // Initialize Mapbox
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: mapStyle === 'dark'
        ? 'mapbox://styles/mapbox/dark-v11'
        : 'mapbox://styles/mapbox/satellite-streets-v12',
      center: [81.92, 21.55],
      zoom: 9.5,
      pitch: 20,
    });

    map.addControl(new mapboxgl.NavigationControl(), 'bottom-right');
    mapRef.current = map;

    map.on('load', () => addMarkers(map, potholes));

    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // Update markers when potholes change
  useEffect(() => {
    if (mapRef.current && mapRef.current.loaded()) {
      addMarkers(mapRef.current, potholes);
    }
  }, [potholes]);

  const addMarkers = useCallback((map, data) => {
    // Remove existing markers
    document.querySelectorAll('.pothole-marker').forEach(m => m.remove());

    data.forEach(p => {
      if (!p.lat || !p.lon) return;
      const el = document.createElement('div');
      el.className = 'pothole-marker';
      el.style.cssText = `
        width: ${p.severity === 'critical' ? 18 : p.severity === 'high' ? 14 : 11}px;
        height: ${p.severity === 'critical' ? 18 : p.severity === 'high' ? 14 : 11}px;
        border-radius: 50%;
        background: ${SEVERITY_COLORS[p.severity] || SEVERITY_COLORS.medium};
        border: 2px solid rgba(255,255,255,0.3);
        cursor: pointer;
        box-shadow: 0 0 ${p.severity === 'critical' ? 12 : 6}px ${SEVERITY_COLORS[p.severity] || SEVERITY_COLORS.medium}80;
        transition: transform 0.15s;
      `;
      el.addEventListener('mouseenter', () => { el.style.transform = 'scale(1.5)'; });
      el.addEventListener('mouseleave', () => { el.style.transform = 'scale(1)'; });
      el.addEventListener('click', () => setSelectedPothole(p));

      const popup = new mapboxgl.Popup({ offset: 15, closeButton: false })
        .setHTML(`
          <div style="font-family:Inter,sans-serif;font-size:12px;color:#1e293b;padding:4px">
            <strong>${p.uuid}</strong><br/>
            ${p.highway_id} KM ${p.km_marker}<br/>
            Risk: <strong style="color:${riskColor(p.risk_score)}">${p.risk_score}/10</strong> |
            ${(p.severity || '').toUpperCase()}
          </div>
        `);

      new mapboxgl.Marker({ element: el })
        .setLngLat([p.lon, p.lat])
        .setPopup(popup)
        .addTo(map);
    });
  }, []);

  const toggleMapStyle = () => {
    const newStyle = mapStyle === 'dark' ? 'satellite' : 'dark';
    setMapStyle(newStyle);
    if (mapRef.current) {
      mapRef.current.setStyle(
        newStyle === 'dark'
          ? 'mapbox://styles/mapbox/dark-v11'
          : 'mapbox://styles/mapbox/satellite-streets-v12'
      );
      mapRef.current.once('style.load', () => addMarkers(mapRef.current, potholes));
    }
  };

  const activePotholes = potholes.filter(p => p.status !== 'verified_repaired');
  const criticalCount = activePotholes.filter(p => p.severity === 'critical').length;

  return (
    <div className="app-layout">
      {/* ── Header ───────────────────────────────────────── */}
      <header className="header">
        <div className="header-brand">
          <div className="header-logo">AP</div>
          <div>
            <div className="header-title">APIS</div>
            <div className="header-subtitle">Autonomous Pothole Intelligence System</div>
          </div>
        </div>
        <div className="header-stats">
          <div className="header-stat">
            <div className="header-stat-value">{analytics.total_active}</div>
            <div className="header-stat-label">Active</div>
          </div>
          <div className="header-stat">
            <div className="header-stat-value">{analytics.total_complaints_filed}</div>
            <div className="header-stat-label">Filed</div>
          </div>
          <div className="header-stat">
            <div className="header-stat-value">{analytics.total_repaired}</div>
            <div className="header-stat-label">Repaired</div>
          </div>
          <div className="header-stat">
            <div className="header-stat-value" style={{color: 'var(--critical)'}}>
              {analytics.total_sla_breached}
            </div>
            <div className="header-stat-label">SLA Breach</div>
          </div>
        </div>
        <div style={{display:'flex',gap:'12px',alignItems:'center'}}>
          <div style={{position:'relative'}}>
            <Bell size={18} color="var(--text-muted)" />
            {criticalCount > 0 && (
              <span style={{
                position:'absolute',top:-4,right:-4,width:14,height:14,borderRadius:'50%',
                background:'var(--critical)',fontSize:9,fontWeight:800,display:'flex',
                alignItems:'center',justifyContent:'center',color:'white'
              }}>{criticalCount}</span>
            )}
          </div>
        </div>
      </header>

      {/* ── Sidebar ──────────────────────────────────────── */}
      <nav className="sidebar">
        <div className="sidebar-section">
          <div className="sidebar-label">Monitoring</div>
          <div className={`sidebar-item ${view === 'map' ? 'active' : ''}`} onClick={() => setView('map')}>
            <MapPin size={18} /><span>Live Map</span>
          </div>
          <div className={`sidebar-item ${view === 'potholes' ? 'active' : ''}`} onClick={() => setView('potholes')}>
            <AlertTriangle size={18} /><span>Potholes</span>
            {criticalCount > 0 && <span className="sidebar-badge">{criticalCount}</span>}
          </div>
          <div className={`sidebar-item ${view === 'complaints' ? 'active' : ''}`} onClick={() => setView('complaints')}>
            <FileText size={18} /><span>Complaints</span>
          </div>
        </div>
        <div className="sidebar-section">
          <div className="sidebar-label">Intelligence</div>
          <div className={`sidebar-item ${view === 'analytics' ? 'active' : ''}`} onClick={() => setView('analytics')}>
            <TrendingUp size={18} /><span>Analytics</span>
          </div>
          <div className={`sidebar-item ${view === 'predictive' ? 'active' : ''}`} onClick={() => setView('predictive')}>
            <Zap size={18} /><span>Predictions</span>
          </div>
          <div className={`sidebar-item ${view === 'stretches' ? 'active' : ''}`} onClick={() => setView('stretches')}>
            <Shield size={18} /><span>Stretches</span>
          </div>
        </div>
        <div className="sidebar-section">
          <div className="sidebar-label">Sources</div>
          <div className="sidebar-item">
            <Satellite size={18} /><span>Sentinel-2</span>
          </div>
          <div className="sidebar-item">
            <Camera size={18} /><span>CCTV ({analytics.source_distribution?.cctv || 0})</span>
          </div>
          <div className="sidebar-item">
            <Smartphone size={18} /><span>Mobile ({analytics.source_distribution?.mobile || 0})</span>
          </div>
        </div>
      </nav>

      {/* ── Map / Content Area ───────────────────────────── */}
      <main className="map-container">
        {view === 'map' && (
          <>
            <div ref={mapContainerRef} style={{width:'100%',height:'100%'}} />
            <div className="map-controls">
              <button className={`map-btn ${mapStyle === 'satellite' ? 'active' : ''}`}
                      onClick={toggleMapStyle}>
                <Layers size={14} />{mapStyle === 'dark' ? 'Satellite' : 'Street'}
              </button>
              <button className={`map-btn ${showHeatmap ? 'active' : ''}`}
                      onClick={() => setShowHeatmap(!showHeatmap)}>
                <Activity size={14} />Heatmap
              </button>
            </div>
          </>
        )}
        {view === 'analytics' && <AnalyticsView analytics={analytics} />}
        {view === 'potholes' && (
          <div style={{padding:20,overflowY:'auto',height:'100%'}}>
            <h2 style={{fontSize:18,fontWeight:700,marginBottom:16}}>All Active Potholes</h2>
            <PotholeList potholes={activePotholes} onSelect={setSelectedPothole} />
          </div>
        )}
      </main>

      {/* ── Right Panel ──────────────────────────────────── */}
      <aside className="right-panel">
        {selectedPothole ? (
          <PotholePassport pothole={selectedPothole} onClose={() => setSelectedPothole(null)} />
        ) : (
          <>
            <KPIGrid analytics={analytics} />
            <RecentDetections potholes={potholes} onSelect={setSelectedPothole} />
            <SeverityChart distribution={analytics.severity_distribution} />
          </>
        )}
      </aside>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// Sub-Components
// ═══════════════════════════════════════════════════════════

function KPIGrid({ analytics }) {
  return (
    <div className="kpi-grid fade-in">
      <div className="kpi-card">
        <div className="kpi-value" style={{color:'var(--critical)'}}>{analytics.total_active}</div>
        <div className="kpi-label">Active Potholes</div>
        <div className="kpi-trend up">↑ {analytics.detections_last_7d} this week</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-value" style={{color:'var(--accent-light)'}}>{analytics.avg_risk_score}</div>
        <div className="kpi-label">Avg Risk Score</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-value" style={{color:'var(--filed)'}}>{analytics.total_complaints_filed}</div>
        <div className="kpi-label">Complaints Filed</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-value" style={{color:'var(--repaired)'}}>{analytics.repairs_verified}</div>
        <div className="kpi-label">Repairs Verified</div>
      </div>
    </div>
  );
}

function RecentDetections({ potholes, onSelect }) {
  const recent = [...potholes]
    .sort((a, b) => new Date(b.first_detected) - new Date(a.first_detected))
    .slice(0, 5);

  return (
    <div className="card fade-in">
      <div className="card-header">
        <div className="card-title"><Clock size={16} />Recent Detections</div>
      </div>
      <div className="pothole-list">
        {recent.map(p => (
          <div key={p.uuid} className="pothole-item" onClick={() => onSelect(p)}>
            <span className={`severity-dot ${severityClass(p.severity)}`} />
            <div className="pothole-item-info">
              <div className="pothole-item-title">{p.highway_id} KM {p.km_marker}</div>
              <div className="pothole-item-meta">
                {p.source_primary?.toUpperCase()} · {timeAgo(p.first_detected)}
              </div>
            </div>
            <div className="pothole-risk" style={{color: riskColor(p.risk_score)}}>
              {p.risk_score}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SeverityChart({ distribution }) {
  const data = Object.entries(distribution || {}).map(([k, v]) => ({
    name: k.charAt(0).toUpperCase() + k.slice(1), value: v, fill: SEVERITY_COLORS[k],
  }));

  return (
    <div className="card fade-in">
      <div className="card-header">
        <div className="card-title"><Activity size={16} />Severity Distribution</div>
      </div>
      <div className="chart-container">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} cx="50%" cy="50%" innerRadius={45} outerRadius={70}
                 paddingAngle={3} dataKey="value" strokeWidth={0}>
              {data.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
            </Pie>
            <Tooltip contentStyle={{background:'#1e293b',border:'1px solid rgba(255,255,255,0.1)',borderRadius:8,fontSize:12}} />
            <Legend iconType="circle" iconSize={8} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function PotholePassport({ pothole, onClose }) {
  const p = pothole;
  return (
    <div className="slide-in">
      <div className="card" style={{marginBottom:12}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'start'}}>
          <div>
            <div style={{fontSize:11,color:'var(--text-muted)',fontWeight:600,letterSpacing:'0.5px',textTransform:'uppercase'}}>
              Pothole Passport
            </div>
            <div style={{fontSize:14,fontWeight:700,marginTop:4}}>{p.uuid}</div>
          </div>
          <button onClick={onClose} style={{
            background:'var(--bg-hover)',border:'1px solid var(--border-glass)',
            color:'var(--text-secondary)',borderRadius:6,padding:'4px 10px',cursor:'pointer',fontSize:12,fontFamily:'var(--font)'
          }}>✕</button>
        </div>

        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginTop:14}}>
          <InfoRow label="Highway" value={`${p.highway_id} KM ${p.km_marker}`} />
          <InfoRow label="GPS" value={`${p.lat?.toFixed(4)}°N, ${p.lon?.toFixed(4)}°E`} />
          <InfoRow label="Severity" value={
            <span className={`severity-badge ${severityClass(p.severity)}`}>
              <span className={`severity-dot ${severityClass(p.severity)}`} />
              {(p.severity || '').toUpperCase()}
            </span>
          } />
          <InfoRow label="Risk Score" value={
            <span style={{fontSize:18,fontWeight:800,color:riskColor(p.risk_score)}}>{p.risk_score}/10</span>
          } />
          <InfoRow label="Area" value={`${p.area_sqm} m²`} />
          <InfoRow label="Depth" value={`${p.depth_cm} cm`} />
          <InfoRow label="Source" value={p.source_primary?.toUpperCase()} />
          <InfoRow label="Confidence" value={`${(p.confidence * 100).toFixed(0)}%`} />
          <InfoRow label="Detected" value={formatDateTime(p.first_detected)} />
          <InfoRow label="Status" value={
            <span className={`status-badge ${p.status?.includes('repaired') ? 'repaired' : p.status?.includes('escalat') ? 'escalated' : p.status?.includes('filed') ? 'filed' : p.status?.includes('pred') ? 'predicted' : 'detected'}`}>
              {STATUS_LABELS[p.status] || p.status}
            </span>
          } />
        </div>
      </div>

      {/* Timeline */}
      <div className="card">
        <div className="card-header">
          <div className="card-title"><Clock size={16} />Lifecycle Timeline</div>
        </div>
        <div className="timeline">
          <TimelineItem event="DETECTED" detail={`Via ${p.source_primary} (${(p.confidence*100).toFixed(0)}%)`} time={p.first_detected} />
          <TimelineItem event="RISK SCORED" detail={`Score: ${p.risk_score}/10 (${p.severity})`} />
          {p.status !== 'detected' && p.status !== 'pred_unconfirmed' && (
            <TimelineItem event="COMPLAINT FILED" detail={`Filed on PG Portal`} />
          )}
          {p.status?.includes('escalat') && (
            <TimelineItem event="ESCALATED" detail={`SLA breach — escalated to higher authority`} />
          )}
          {p.status === 'verified_repaired' && (
            <TimelineItem event="VERIFIED REPAIRED" detail="SSIM > 0.88 + citizen confirmation" />
          )}
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div>
      <div style={{fontSize:10,color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'0.3px'}}>{label}</div>
      <div style={{fontSize:13,fontWeight:600,marginTop:2}}>{value || '—'}</div>
    </div>
  );
}

function TimelineItem({ event, detail, time }) {
  return (
    <div className="timeline-item">
      <div className="timeline-dot"><ChevronRight size={12} /></div>
      <div className="timeline-content">
        <div className="timeline-event">{event}</div>
        {detail && <div className="timeline-detail">{detail}</div>}
        {time && <div className="timeline-time">{formatDateTime(time)}</div>}
      </div>
    </div>
  );
}

function PotholeList({ potholes, onSelect }) {
  return (
    <div className="pothole-list">
      {potholes.map(p => (
        <div key={p.uuid} className="pothole-item" onClick={() => onSelect(p)}>
          <span className={`severity-dot ${severityClass(p.severity)}`} />
          <div className="pothole-item-info">
            <div className="pothole-item-title">{p.uuid}</div>
            <div className="pothole-item-meta">
              {p.highway_id} KM {p.km_marker} · {p.source_primary?.toUpperCase()} ·
              {' '}{formatDate(p.first_detected)}
            </div>
          </div>
          <span className={`severity-badge ${severityClass(p.severity)}`}>
            {(p.severity || '').toUpperCase()}
          </span>
          <div className="pothole-risk" style={{color: riskColor(p.risk_score)}}>
            {p.risk_score}
          </div>
        </div>
      ))}
    </div>
  );
}

function AnalyticsView({ analytics }) {
  const trendData = (analytics.monthly_trend || []).map(m => ({
    ...m, month: m.month ? m.month.slice(5, 7) + '/' + m.month.slice(2, 4) : '',
  }));

  const sourceData = Object.entries(analytics.source_distribution || {}).map(([k, v]) => ({
    name: k.charAt(0).toUpperCase() + k.slice(1), value: v,
  }));
  const sourceColors = ['#6366f1', '#06b6d4', '#f97316', '#a855f7'];

  return (
    <div style={{padding:24,overflowY:'auto',height:'100%'}}>
      <h2 style={{fontSize:20,fontWeight:800,marginBottom:20,letterSpacing:'-0.3px'}}>
        <TrendingUp size={20} style={{display:'inline',verticalAlign:'middle',marginRight:8}} />
        Analytics Dashboard
      </h2>

      {/* KPI row */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:16,marginBottom:24}}>
        {[
          { label: 'Active Potholes', val: analytics.total_active, color: 'var(--critical)' },
          { label: 'Complaints Filed', val: analytics.total_complaints_filed, color: 'var(--filed)' },
          { label: 'Repairs Verified', val: analytics.repairs_verified, color: 'var(--repaired)' },
          { label: 'SLA Breached', val: analytics.total_sla_breached, color: 'var(--escalated)' },
        ].map(kpi => (
          <div key={kpi.label} className="kpi-card">
            <div className="kpi-value" style={{color:kpi.color}}>{kpi.val}</div>
            <div className="kpi-label">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
        <div className="card">
          <div className="card-header">
            <div className="card-title">Monthly Detection vs Repair Trend</div>
          </div>
          <div style={{height:260}}>
            <ResponsiveContainer>
              <BarChart data={trendData} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip contentStyle={{background:'#1e293b',border:'1px solid rgba(255,255,255,0.1)',borderRadius:8,fontSize:12}} />
                <Legend />
                <Bar dataKey="detected" name="Detected" fill="#ef4444" radius={[4,4,0,0]} />
                <Bar dataKey="repaired" name="Repaired" fill="#10b981" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div className="card-title">Detection Source Distribution</div>
          </div>
          <div style={{height:260}}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={sourceData} cx="50%" cy="50%" innerRadius={55} outerRadius={85}
                     paddingAngle={3} dataKey="value" strokeWidth={0}>
                  {sourceData.map((_, i) => <Cell key={i} fill={sourceColors[i % sourceColors.length]} />)}
                </Pie>
                <Tooltip contentStyle={{background:'#1e293b',border:'1px solid rgba(255,255,255,0.1)',borderRadius:8,fontSize:12}} />
                <Legend iconType="circle" iconSize={8} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
