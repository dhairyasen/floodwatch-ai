const analyzeBtn = document.getElementById('analyzeBtn');
const loadingDiv = document.getElementById('loading');
const errorDiv = document.getElementById('error');
const resultsCard = document.getElementById('results');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');

// Nominatim API based autocomplete — covers all of India (cities, towns, villages, districts)
let nominatimTimeout = null;
let selectedCoords = null;

function setupAutocomplete() {
    const input = document.getElementById('location');

    // Create dropdown container
    const dropdown = document.createElement('div');
    dropdown.id = 'cityDropdown';
    dropdown.style.cssText = `
        position: absolute;
        background: white;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        max-height: 260px;
        overflow-y: auto;
        z-index: 1000;
        display: none;
        width: 100%;
        top: 100%;
        left: 0;
    `;
    input.parentElement.style.position = 'relative';
    input.parentElement.appendChild(dropdown);

    input.addEventListener('input', () => {
        const query = input.value.trim();
        selectedCoords = null; // reset coords on new input
        dropdown.innerHTML = '';

        if (query.length < 3) {
            dropdown.style.display = 'none';
            return;
        }

        // Show loading indicator
        dropdown.innerHTML = `<div style="padding:10px 14px; color:#64748b; font-size:13px;">Searching...</div>`;
        dropdown.style.display = 'block';

        // Debounce — wait 400ms after user stops typing
        clearTimeout(nominatimTimeout);
        nominatimTimeout = setTimeout(async () => {
            try {
                const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&countrycodes=in&format=json&addressdetails=1&limit=8`;
                const res = await fetch(url, {
                    headers: { 'Accept-Language': 'en' }
                });
                const results = await res.json();

                dropdown.innerHTML = '';

                if (results.length === 0) {
                    dropdown.innerHTML = `<div style="padding:10px 14px; color:#64748b; font-size:13px;">No results found</div>`;
                    return;
                }

                results.forEach(place => {
                    const parts = place.display_name.split(',');
                    const cityName = parts[0].trim();
                    const stateName = parts.slice(1, 3).join(',').trim();
                    const item = document.createElement('div');
                    item.style.cssText = `
                        padding: 10px 14px;
                        cursor: pointer;
                        font-size: 14px;
                        color: #1e293b;
                        border-bottom: 1px solid #f1f5f9;
                        line-height: 1.4;
                    `;
                    item.innerHTML = `
                        <div style="font-weight:600;">${cityName}</div>
                        <div style="font-size:11px; color:#64748b;">${stateName}</div>
                    `;
                    item.addEventListener('mouseenter', () => item.style.background = '#f0f9ff');
                    item.addEventListener('mouseleave', () => item.style.background = 'white');
                    item.addEventListener('mousedown', () => {
                        input.value = `${cityName}, ${stateName}`;
                        selectedCoords = { lat: parseFloat(place.lat), lon: parseFloat(place.lon) };
                        dropdown.style.display = 'none';
                    });
                    dropdown.appendChild(item);
                });

                dropdown.style.display = 'block';
            } catch (err) {
                dropdown.innerHTML = `<div style="padding:10px 14px; color:#ef4444; font-size:13px;">Search failed, type manually</div>`;
            }
        }, 400);
    });

    // Hide dropdown on outside click
    document.addEventListener('click', (e) => {
        if (!input.parentElement.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') dropdown.style.display = 'none';
    });
}

// Initialize autocomplete
setupAutocomplete();

function selectCity(city) {
    document.getElementById('location').value = city;
    selectedCoords = null; // will fall back to config.py coordinates
    const dropdown = document.getElementById('cityDropdown');
    if (dropdown) dropdown.style.display = 'none';
}

function showError(message) {
    errorDiv.style.display = 'flex';
    document.getElementById('errorMessage').textContent = message;
}

function updateProgress(percent, text) {
    progressBar.style.width = percent + '%';
    progressText.textContent = text;
}

analyzeBtn.addEventListener('click', async () => {
    const location = document.getElementById('location').value;
    const beforeStartDate = document.getElementById('beforeStartDate').value;
    const beforeEndDate = document.getElementById('beforeEndDate').value;
    const afterStartDate = document.getElementById('afterStartDate').value;
    const afterEndDate = document.getElementById('afterEndDate').value;
    
    if (!location || !beforeStartDate || !beforeEndDate || !afterStartDate || !afterEndDate) {
        showError('Please fill in all fields');
        return;
    }
    
    // Hide previous results and errors
    errorDiv.style.display = 'none';
    resultsCard.style.display = 'none';
    
    // Show loading
    loadingDiv.style.display = 'block';
    
    // Simulate progress
    updateProgress(0, 'Initializing...');
    setTimeout(() => updateProgress(20, 'Fetching satellite data...'), 500);
    setTimeout(() => updateProgress(40, 'Processing imagery...'), 1500);
    setTimeout(() => updateProgress(60, 'Analyzing water patterns...'), 3000);
    setTimeout(() => updateProgress(80, 'Computing metrics...'), 4500);
    
    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                location,
                lat: selectedCoords ? selectedCoords.lat : null,
                lon: selectedCoords ? selectedCoords.lon : null,
                before_start_date: beforeStartDate,
                before_end_date: beforeEndDate,
                after_start_date: afterStartDate,
                after_end_date: afterEndDate
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Analysis failed');
        }
        
        updateProgress(100, 'Complete!');
        setTimeout(() => displayResults(data), 500);
        
    } catch (error) {
        showError(error.message);
    } finally {
        setTimeout(() => {
            loadingDiv.style.display = 'none';
        }, 600);
    }
});

function displayResults(data) {
    // Update header
    document.getElementById('resultLocation').textContent = data.location_name;
    document.getElementById('resultPeriod').textContent = 
        `Analysis Period: ${data.start_date} to ${data.end_date}`;
    
    // Display results
    const resultsHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px;">
            <div style="background: linear-gradient(135deg, #3b82f6, #2563eb); padding: 20px; border-radius: 12px; color: white;">
                <div style="font-size: 0.9rem; opacity: 0.9; margin-bottom: 5px;">Water Before</div>
                <div style="font-size: 2rem; font-weight: 700;">${data.water_before} km²</div>
            </div>
            <div style="background: linear-gradient(135deg, #ef4444, #dc2626); padding: 20px; border-radius: 12px; color: white;">
                <div style="font-size: 0.9rem; opacity: 0.9; margin-bottom: 5px;">Water After</div>
                <div style="font-size: 2rem; font-weight: 700;">${data.water_after} km²</div>
            </div>
            <div style="background: linear-gradient(135deg, #f59e0b, #d97706); padding: 20px; border-radius: 12px; color: white;">
                <div style="font-size: 0.9rem; opacity: 0.9; margin-bottom: 5px;">New Flooded Area</div>
                <div style="font-size: 2rem; font-weight: 700;">${data.new_flooded_area} km²</div>
            </div>
            <div style="background: linear-gradient(135deg, #8b5cf6, #7c3aed); padding: 20px; border-radius: 12px; color: white;">
                <div style="font-size: 0.9rem; opacity: 0.9; margin-bottom: 5px;">Change</div>
                <div style="font-size: 2rem; font-weight: 700;">${data.water_coverage_change > 0 ? '+' : ''}${data.water_coverage_change}%</div>
            </div>
        </div>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px;">
            <div style="text-align: center;">
                <h4 style="margin-bottom: 15px; color: #1e293b;">Water Coverage</h4>
                <img src="/outputs/water_coverage.png?t=${Date.now()}" style="width: 100%; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            </div>
            <div style="text-align: center;">
                <h4 style="margin-bottom: 15px; color: #1e293b;">Water Composition</h4>
                <img src="/outputs/water_composition.png?t=${Date.now()}" style="width: 100%; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            </div>
        </div>
        
        <div style="margin-top: 30px;">
            <h4 style="margin-bottom: 15px; color: #1e293b;"><i class="fas fa-map"></i> Interactive Flood Map</h4>
            <iframe src="/outputs/flood_map.html?t=${Date.now()}" style="width: 100%; height: 600px; border: none; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"></iframe>
        </div>
        
        <div style="margin-top: 30px; text-align: center;">
            <img src="/outputs/summary.png?t=${Date.now()}" style="width: 100%; max-width: 800px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        </div>
    `;
    
    document.getElementById('resultsDisplay').innerHTML = resultsHTML;
    resultsCard.style.display = 'block';
    resultsCard.scrollIntoView({ behavior: 'smooth' });
}
/* ============================================================
   Phase 2 — Alarm banner display
   ============================================================ */
const ALARM_COLORS = {
    NONE:     '#10b981',
    LOW:      '#f59e0b',
    MEDIUM:   '#f97316',
    HIGH:     '#ef4444',
    CRITICAL: '#dc2626',
};

function showAlarmBanner(alarm) {
    if (!alarm || !alarm.severity) return;

    const banner = document.getElementById('alarmBanner');
    const icon   = document.getElementById('alarmIcon');
    const title  = document.getElementById('alarmTitle');
    const msg    = document.getElementById('alarmMsg');
    const color  = ALARM_COLORS[alarm.severity] || '#64748b';

    icon.textContent  = alarm.severity_icon || '⚠️';
    title.textContent = `Flood Severity: ${alarm.severity}`;
    title.style.color = color;
    msg.textContent   = alarm.message || '';

    banner.style.borderLeft = `4px solid ${color}`;
    banner.style.display = 'flex';

    // Auto-dismiss NONE/LOW after 6s
    if (alarm.severity === 'NONE' || alarm.severity === 'LOW') {
        setTimeout(() => { banner.style.display = 'none'; }, 6000);
    }
}

/* ============================================================
   Phase 2 — Patch displayResults to show alarm
   ============================================================ */
const _origDisplayResults = displayResults;
function displayResults(data) {
    _origDisplayResults(data);
    if (data.alarm) {
        showAlarmBanner(data.alarm);
        loadAlarmHistory();   // refresh history list after new analysis
    }
}

/* ============================================================
   Phase 2 — Subscription handlers
   ============================================================ */
async function handleSubscribe() {
    const email  = document.getElementById('subEmail').value.trim();
    const name   = document.getElementById('subName').value.trim();
    const cities = document.getElementById('subCities').value
        .split(',').map(c => c.trim()).filter(Boolean);
    const status = document.getElementById('subscribeStatus');

    if (!email) {
        showSubscribeStatus('Please enter a valid email address.', 'error');
        return;
    }

    const btn = document.getElementById('subscribeBtn');
    btn.disabled = true;
    btn.querySelector('span').textContent = 'Subscribing...';

    try {
        const res = await fetch('/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, name, cities }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Subscription failed');
        const verb = data.status === 'updated' ? 'updated' : 'confirmed';
        showSubscribeStatus(`✅ Subscription ${verb} for ${email}. Weekly reports will arrive every Monday.`, 'success');
    } catch (err) {
        showSubscribeStatus(`❌ ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.querySelector('span').textContent = 'Subscribe to Weekly Reports';
    }
}

async function handleUnsubscribe() {
    const email = document.getElementById('subEmail').value.trim();
    if (!email) {
        showSubscribeStatus('Enter your email first to unsubscribe.', 'error');
        return;
    }
    try {
        const res = await fetch('/unsubscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
        });
        const data = await res.json();
        showSubscribeStatus(`✅ ${email} has been unsubscribed successfully.`, 'success');
    } catch (err) {
        showSubscribeStatus(`❌ ${err.message}`, 'error');
    }
}

function showSubscribeStatus(msg, type) {
    const el = document.getElementById('subscribeStatus');
    el.textContent = msg;
    el.className = `subscribe-status ${type}`;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; }, 8000);
}

/* ============================================================
   Phase 2 — Alarm history list
   ============================================================ */
async function loadAlarmHistory() {
    const container = document.getElementById('alarmHistoryList');
    const btn = document.getElementById('loadMoreBtn');
    try {
        const res = await fetch('/alarms/history?limit=10');
        const data = await res.json();

        if (!Array.isArray(data) || data.length === 0) {
            container.innerHTML = `
                <p style="color:var(--gray); font-size:13px; margin-top:8px; font-style:italic;">
                    No alarm history yet. Run an analysis to generate your first alarm record.
                </p>`;
            btn.style.display = 'none';
            return;
        }

        container.innerHTML = data.map(a => {
            const color = ALARM_COLORS[a.severity] || '#64748b';
            const ts = (a.timestamp || '').slice(0, 16).replace('T', ' ');
            const flood = (a.metrics?.new_flooded_area_km2 ?? 0).toFixed(2);
            return `
            <div class="alarm-history-item">
                <div class="ah-icon">${a.severity_icon || '⚠️'}</div>
                <div class="ah-body">
                    <div class="ah-location">${a.location_name || 'Unknown'}</div>
                    <div class="ah-time">${ts}</div>
                </div>
                <span class="ah-severity"
                      style="background:${color}22; color:${color}; border:1px solid ${color}40;">
                    ${a.severity}
                </span>
                <div class="ah-flood">${flood} km²</div>
            </div>`;
        }).join('');

        btn.style.display = 'block';

    } catch (err) {
        container.innerHTML = `<p style="color:var(--gray); font-size:13px;">Could not load history (server may be offline).</p>`;
        btn.style.display = 'none';
    }
}

// Load on page init
loadAlarmHistory();