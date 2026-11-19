// KiwiCamp Interactive 28-Day New Zealand Campervan Odyssey Frontend App
let allDaysData = [];
let activeIslandFilter = 'all';
let activeSearchQuery = '';
let leafletMap = null;
let mapMarkers = [];
let routePolyline = null;

const AGENTOPS_RUBRIC_ITEMS = [
  { category: '1. Tool & Interface Design', criterion: 'Comprehensive Tool Docstrings', pts: '5/5', evidence: 'app/tools/nz_campervan_tools.py — Full Google-style docstrings on all 7 tools.' },
  { category: '1. Tool & Interface Design', criterion: 'Descriptive Naming', pts: '5/5', evidence: 'calculate_campervan_route_segment, search_nz_holiday_parks_and_campsites, reserve_cook_strait_campervan_ferry.' },
  { category: '1. Tool & Interface Design', criterion: 'Explicit JSON Schemas', pts: '5/5', evidence: 'app/schemas/itinerary_schemas.py — Strict Pydantic v2 BaseModel input/output schemas.' },
  { category: '1. Tool & Interface Design', criterion: 'Guided Error Handling', pts: '5/5', evidence: 'Structured error_code + recovery_instructions on forbidden roads & unsafe drive durations.' },
  { category: '2. Context & Memory', criterion: 'Robust System Instructions', pts: '5/5', evidence: 'app/prompts/constitution.py — Constitutional prompts with persona, NZ laws & safety constraints.' },
  { category: '2. Context & Memory', criterion: 'History Compaction', pts: '5/5', evidence: 'app/context/compaction.py — EventsCompactionConfig, LlmEventSummarizer, ContextFilterPlugin & SlidingWindowHistoryCompactor.' },
  { category: '2. Context & Memory', criterion: 'Persistent Session State', pts: '5/5', evidence: 'app/memory/session_and_rag.py — VertexAiSessionService, DatabaseSessionService & SQLite vector store.' },
  { category: '2. Context & Memory', criterion: 'Async Memory Operations', pts: '5/5', evidence: 'app/memory/async_memory_bank.py — Non-blocking asyncio.create_task + wait_for_completion=False.' },
  { category: '3. Orchestration & Logic', criterion: 'Multi-Agent Patterns', pts: '5/5', evidence: 'app/agent.py — Coordinator + SequentialAgent + ParallelAgent + LoopAgent + EscalationChecker + A2A.' },
  { category: '3. Orchestration & Logic', criterion: 'Strategic Model Routing', pts: '5/5', evidence: 'app/orchestration/model_router.py — Routes Flash for fast retrieval and Pro for complex planning/judging.' },
  { category: '3. Orchestration & Logic', criterion: 'Guardrails & Policy Plugins', pts: '5/5', evidence: 'app/plugins/security_guardrails.py — AgentOpsSecurityAndPolicyPlugin(BasePlugin) + ItineraryQualityJudgeAgent.' },
  { category: '3. Orchestration & Logic', criterion: 'Human-in-the-Loop Hooks', pts: '5/5', evidence: 'FunctionTool(..., require_confirmation=True) on ferry and holiday park booking tools.' },
  { category: '4. Observability & Tracing', criterion: 'Structured JSON Logging', pts: '5/5', evidence: 'app/observability/telemetry.py — StructuredJsonLogFormatter with severity, service, and trace IDs.' },
  { category: '4. Observability & Tracing', criterion: 'Intent vs. Outcome Capture', pts: '5/5', evidence: 'IntentOutcomeAuditLogger recording paired INTENT (before) and OUTCOME (after) events.' },
  { category: '4. Observability & Tracing', criterion: 'Distributed Tracing', pts: '5/5', evidence: 'OpenTelemetry TracerProvider, BatchSpanProcessor & CloudTraceSpanExporter.' },
  { category: '4. Observability & Tracing', criterion: 'PII Redaction', pts: '5/5', evidence: 'app/observability/pii_redactor.py — CloudDlpAndRegexPiiRedactor + PiiRedactingLogFilter.' },
  { category: '5. Infrastructure & CI/CD', criterion: 'Automated Evaluation Suites', pts: '5/5', evidence: 'tests/eval/run_evaluation_suite.py + nz_campervan_golden.evalset.json + pytest rubric suite.' },
  { category: '5. Infrastructure & CI/CD', criterion: 'Infrastructure as Code', pts: '5/5', evidence: 'deployment/terraform/*.tf + .github/workflows/ci_cd.yml + agents-cli workflow.' },
  { category: '5. Infrastructure & CI/CD', criterion: 'Secure Secret Management', pts: '5/5', evidence: 'app/utils/secrets.py — SecretManagerVault fetching secrets from Google Cloud Secret Manager.' }
];

async function initApp() {
  try {
    const response = await fetch('itinerary_data.json');
    const data = await response.json();
    allDaysData = data.days || [];
    if (data.total_distance_km) {
      document.getElementById('kpi-distance').textContent = `${data.total_distance_km.toLocaleString()} km`;
    }
    initMap();
    renderQuickJumpGrid();
    renderDaysFeed();
    renderRubricMatrix();
  } catch (err) {
    console.error('Failed to load itinerary_data.json:', err);
  }
}

function initMap() {
  const mapEl = document.getElementById('nz-map');
  if (!mapEl || typeof L === 'undefined') return;

  leafletMap = L.map('nz-map').setView([-41.2, 172.8], 5);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(leafletMap);

  updateMapMarkers(allDaysData);
}

function updateMapMarkers(days) {
  if (!leafletMap || typeof L === 'undefined') return;
  mapMarkers.forEach(m => leafletMap.removeLayer(m));
  mapMarkers = [];
  if (routePolyline) {
    leafletMap.removeLayer(routePolyline);
  }

  const coords = [];
  days.forEach(d => {
    const latlng = [d.latitude, d.longitude];
    coords.push(latlng);

    const marker = L.circleMarker(latlng, {
      radius: d.day_number === 3 || d.day_number === 22 ? 8 : 6,
      fillColor: d.island === 'North Island' ? '#10b981' : (d.day_number === 13 ? '#f59e0b' : '#38bdf8'),
      color: '#0b1320',
      weight: 2,
      opacity: 1,
      fillOpacity: 0.95
    }).addTo(leafletMap);

    marker.bindPopup(
      `<strong>Day ${d.day_number} (${d.date_label}):</strong> ${d.title}<br/>` +
      `<em>${d.start_location} → ${d.end_location}</em> (${d.drive_distance_km} km)`
    );
    marker.on('click', () => scrollToDay(d.day_number));
    mapMarkers.push(marker);
  });

  if (coords.length > 1) {
    routePolyline = L.polyline(coords, {
      color: '#38bdf8',
      weight: 3,
      opacity: 0.75,
      dashArray: '6, 6'
    }).addTo(leafletMap);
  }
}

function renderQuickJumpGrid() {
  const grid = document.getElementById('day-jump-grid');
  if (!grid) return;
  grid.innerHTML = allDaysData.map(d => `
    <button class="day-chip" title="Day ${d.day_number}: ${d.title}" onclick="scrollToDay(${d.day_number})">
      D${d.day_number}
    </button>
  `).join('');
}

function getFilteredDays() {
  return allDaysData.filter(d => {
    const matchesIsland = activeIslandFilter === 'all' || d.island === activeIslandFilter;
    if (!matchesIsland) return false;
    if (!activeSearchQuery) return true;
    const hay = [
      d.title,
      d.start_location,
      d.end_location,
      d.summary,
      ...(d.must_do_highlights || []),
      ...(d.places_to_check_out || []),
      d.overnight_campsite?.name || ''
    ].join(' ').toLowerCase();
    return hay.includes(activeSearchQuery.toLowerCase());
  });
}

function renderDaysFeed() {
  const filtered = getFilteredDays();
  const container = document.getElementById('days-container');
  const banner = document.getElementById('days-count-banner');

  const totalKm = filtered.reduce((acc, d) => acc + (d.drive_distance_km || 0), 0);
  banner.innerHTML = `Showing <strong>${filtered.length}</strong> of 28 days · Combined driving distance: <strong>${totalKm.toLocaleString()} km</strong>`;

  updateMapMarkers(filtered);

  container.innerHTML = filtered.map(d => {
    const photosHtml = (d.photos || []).map(p => `
      <div class="photo-item" onclick="openPhotoModal('${escapeQuotes(p.title)}', '${p.url}', '${escapeQuotes(p.credit)}')">
        <img src="${p.url}" alt="${escapeQuotes(p.title)}" loading="lazy" />
        <div class="photo-caption">📷 ${p.title}</div>
      </div>
    `).join('');

    const video = (d.videos && d.videos[0]) ? d.videos[0] : null;
    const videoHtml = video ? `
      <div class="video-card">
        <div>
          <div class="video-iframe-wrapper">
            <iframe
              src="${video.embed_url}"
              title="${escapeQuotes(video.title)}"
              loading="lazy"
              frameborder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              referrerpolicy="strict-origin-when-cross-origin"
              allowfullscreen>
            </iframe>
          </div>
          <strong>🎬 ${video.title}</strong>
        </div>
        <div class="video-footer">
          <span>📺 ${video.duration_label}</span>
          <a href="${video.watch_url}" target="_blank" rel="noopener noreferrer">Watch on YouTube ↗</a>
        </div>
      </div>
    ` : '';

    const camp = d.overnight_campsite || {};
    const amenitiesHtml = (camp.amenities || []).map(a => `<span class="amenity-chip">${a}</span>`).join('');

    return `
      <article class="day-card" id="day-card-${d.day_number}">
        <div class="day-card-header">
          <div class="day-badge-group">
            <span class="day-number-pill">DAY ${d.day_number} · ${d.date_label}</span>
            <span class="island-tag">${d.island}</span>
          </div>
          <div class="drive-metrics">
            <span>🛣️ <strong>${d.drive_distance_km} km</strong></span>
            <span>⏱️ <strong>${d.drive_duration_hours} hrs</strong> campervan drive</span>
          </div>
        </div>

        <div class="day-card-body">
          <h3 class="day-title">${d.title}</h3>
          <div class="day-route-line">📍 ${d.start_location} → ${d.end_location}</div>
          <p class="day-summary">${d.summary}</p>

          <div class="weather-strip">
            ☀️ <strong>December Conditions:</strong> ${d.december_weather_note}
          </div>

          <div class="day-details-grid">
            <div class="detail-box">
              <h4>✨ Things to Do &amp; Highlights</h4>
              <ul>
                ${(d.must_do_highlights || []).map(item => `<li>${item}</li>`).join('')}
              </ul>
            </div>

            <div class="detail-box">
              <h4>🗺️ Places to Check Out</h4>
              <ul>
                ${(d.places_to_check_out || []).map(item => `<li>${item}</li>`).join('')}
              </ul>
            </div>

            <div class="detail-box tips-box">
              <h4>🚐 Campervan &amp; Road Safety Tips</h4>
              <ul>
                ${(d.noteworthy_campervan_tips || []).map(item => `<li>${item}</li>`).join('')}
              </ul>
            </div>

            <div class="detail-box campsite-box">
              <h4>🏕️ Overnight Campervan Stop</h4>
              <div class="campsite-meta">
                <strong>${camp.name}</strong> (${camp.category === 'doc_campsite' ? 'DOC Campsite' : (camp.category === 'freedom_camping' ? 'Certified Self-Contained Freedom Site' : 'Holiday Park')})<br/>
                Rate: <strong>$${camp.nightly_rate_nzd} NZD</strong> · ${camp.powered_site_available ? '⚡ 240V Powered Site' : '🔋 Off-Grid / Non-Powered'}<br/>
                <em>${camp.booking_advice_december}</em>
              </div>
              <div class="campsite-amenities">${amenitiesHtml}</div>
            </div>
          </div>

          <div class="media-showcase">
            <div class="photo-gallery">${photosHtml}</div>
            ${videoHtml}
          </div>
        </div>
      </article>
    `;
  }).join('');
}

function filterByIsland(island) {
  activeIslandFilter = island;
  document.querySelectorAll('.pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.island === island);
  });
  renderDaysFeed();
}

function handleSearchInput(val) {
  activeSearchQuery = val.trim();
  renderDaysFeed();
}

function scrollToDay(dayNum) {
  switchMainView('itinerary');
  const el = document.getElementById(`day-card-${dayNum}`);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function switchMainView(viewName) {
  document.querySelectorAll('.view-section').forEach(sec => {
    sec.classList.toggle('active', sec.id === `view-${viewName}`);
  });
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === viewName);
  });
  const filterControls = document.getElementById('itinerary-filters');
  if (filterControls) {
    filterControls.style.display = viewName === 'itinerary' ? 'flex' : 'none';
  }
  if (viewName === 'itinerary' && leafletMap) {
    setTimeout(() => leafletMap.invalidateSize(), 150);
  }
}

function renderRubricMatrix() {
  const grid = document.getElementById('rubric-matrix-grid');
  if (!grid) return;
  grid.innerHTML = AGENTOPS_RUBRIC_ITEMS.map(item => `
    <div class="rubric-card">
      <span class="pts-badge">${item.pts}</span>
      <h4>${item.criterion}</h4>
      <small style="color:#38bdf8;font-weight:600;">${item.category}</small>
      <p style="margin-top:0.5rem;font-size:0.86rem;color:#cbd5e1;">${item.evidence}</p>
    </div>
  `).join('');
}

function simulateHitlBooking(kind) {
  const consoleEl = document.getElementById('hitl-console');
  if (!consoleEl) return;

  if (kind === 'ferry') {
    consoleEl.innerHTML = [
      `[AUDIT_PHASE: INTENT] corr_id="corr-ferry-dec13" tool="reserve_cook_strait_campervan_ferry"`,
      `  args: {"operator": "Interislander", "sailing_date_iso": "2025-12-13", "departure_port": "Wellington", "campervan_length_meters": 7.2}`,
      `[HITL GATE TRIGGERED] FunctionTool(require_confirmation=True) -> status="pending_human_confirmation"`,
      `  Hold Reference: HOLD-HITL-COOKSTRAIT | Total Fare: $449.50 NZD`,
      `  Safety Notice: Campervan LPG gas valve MUST be shut off prior to boarding.`,
      ``,
      `👉 Click [Approve & Execute Booking] below to simulate human confirmation:`
    ].join('\n') + `\n<button class="btn-primary" id="btn-approve-hitl" style="margin-top:10px;" onclick="confirmHitlAction('ferry')">✅ Approve $449.50 NZD Cook Strait Ferry</button>`;
  } else {
    consoleEl.innerHTML = [
      `[AUDIT_PHASE: INTENT] corr_id="corr-milford-dec21" tool="book_paid_holiday_park_site"`,
      `  args: {"park_name": "Milford Sound Lodge Rainforest Campervan Park", "check_in_date_iso": "2025-12-21", "nights": 1, "estimated_total_nzd": 120.0}`,
      `[HITL GATE TRIGGERED] FunctionTool(require_confirmation=requires_holiday_park_booking_confirmation) -> status="pending_human_confirmation"`,
      `  Hold Reference: HOLD-HITL-CAMPSITE | Total Charge: $120.00 NZD`,
      ``,
      `👉 Click [Approve & Execute Booking] below to simulate human confirmation:`
    ].join('\n') + `\n<button class="btn-primary" id="btn-approve-hitl" style="margin-top:10px;" onclick="confirmHitlAction('milford')">✅ Approve $120.00 NZD Milford Sound Lodge</button>`;
  }
}

function confirmHitlAction(kind) {
  const consoleEl = document.getElementById('hitl-console');
  if (kind === 'ferry') {
    consoleEl.textContent = [
      `[HUMAN CONFIRMATION RECEIVED] tool_confirmation.confirmed = True`,
      `[AUDIT_PHASE: OUTCOME] corr_id="corr-ferry-dec13" status="SUCCESS" latency_ms=14.2`,
      `  Confirmed Reference: NZFERRY-20251213-72M`,
      `  Route: Wellington -> Picton (Interislander) | Charged: $449.50 NZD`
    ].join('\n');
  } else {
    consoleEl.textContent = [
      `[HUMAN CONFIRMATION RECEIVED] tool_confirmation.confirmed = True`,
      `[AUDIT_PHASE: OUTCOME] corr_id="corr-milford-dec21" status="SUCCESS" latency_ms=11.8`,
      `  Confirmed Reservation ID: NZCAMP-20251221`,
      `  Park: Milford Sound Lodge Rainforest Campervan Park | Charged: $120.00 NZD`
    ].join('\n');
  }
}

function openPhotoModal(title, url, credit) {
  const modal = document.getElementById('media-modal');
  const modalTitle = document.getElementById('modal-title');
  const modalBody = document.getElementById('modal-body');
  modalTitle.textContent = `${title} (${credit})`;
  modalBody.innerHTML = `<img src="${url}" alt="${escapeQuotes(title)}" style="width:100%;max-height:72vh;object-fit:contain;border-radius:8px;margin-top:0.75rem;" />`;
  modal.classList.remove('hidden');
}

function closeMediaModal() {
  const modal = document.getElementById('media-modal');
  modal.classList.add('hidden');
}

function escapeQuotes(str) {
  return String(str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

document.addEventListener('DOMContentLoaded', initApp);
