let tvData = [];
// Legacy client-side Resolume integration removed. The UI keeps a header
// link to access the Resolume web UI directly, but all client-side calls
// to server-side Resolume endpoints have been removed.
let currentRemoteTV = null; // Track which TV the remote modal is controlling

let isGlobalCommandInProgress = false;

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `fixed top-20 right-4 px-6 py-3 rounded-lg shadow-lg text-white z-50 transition-opacity duration-300 ${type === 'success' ? 'bg-green-600' :
        type === 'error' ? 'bg-red-600' :
            'bg-blue-600'
        }`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function setGlobalRemoteLoading(loading) {
    isGlobalCommandInProgress = loading;
    const buttons = document.querySelectorAll('#global-remote-modal button[onclick^="sendGlobalKey"]');
    buttons.forEach(btn => {
        if (loading) {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'wait';
        } else {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        }
    });
}

async function sendGlobalKey(key) {
    if (isGlobalCommandInProgress) return;

    try {
        setGlobalRemoteLoading(true);
        showToast('Sending command to all TVs...', 'info');

        const res = await fetch('/api/tvs/broadcast-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key })
        });

        if (res.ok) {
            const data = await res.json();
            console.log(`Global key ${key} sent:`, data);
            showToast(`✓ Command sent to ${data.success_count}/${data.total} TVs`, 'success');
        } else {
            const error = await res.text();
            console.error(`Failed to send global key ${key}:`, error);
            showToast(`Failed to send command to all TVs`, 'error');
        }
    } catch (error) {
        console.error(`Error sending global key ${key}:`, error);
        showToast(`Error sending command to all TVs`, 'error');
    } finally {
        setGlobalRemoteLoading(false);
    }
}

function openRemoteModal(ip, name) {
    currentRemoteTV = { ip, name };
    document.getElementById('remote-modal-title').textContent = `Remote: ${name}`;
    const modal = document.getElementById('tv-remote-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeRemoteModal(event) {
    // If event is provided and target is not the backdrop, don't close
    if (event && event.target.id !== 'tv-remote-modal') {
        return;
    }

    const modal = document.getElementById('tv-remote-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    currentRemoteTV = null;
}

function openGlobalRemote() {
    const modal = document.getElementById('global-remote-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeGlobalRemote(event) {
    // If event is provided and target is not the backdrop, don't close
    if (event && event.target.id !== 'global-remote-modal') {
        return;
    }

    const modal = document.getElementById('global-remote-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

async function sendIndividualKey(key) {
    if (!currentRemoteTV) {
        console.error('No TV selected for remote control');
        return;
    }

    try {
        const res = await fetch(`/api/tvs/${encodeURIComponent(currentRemoteTV.ip)}/send-key`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key })
        });

        if (res.ok) {
            const data = await res.json();
            console.log(`Key ${key} sent to ${currentRemoteTV.name}:`, data);
        } else {
            const error = await res.text();
            console.error(`Failed to send key ${key} to ${currentRemoteTV.name}:`, error);
            alert(`Failed to send command to ${currentRemoteTV.name}`);
        }
    } catch (error) {
        console.error(`Error sending key ${key} to ${currentRemoteTV.name}:`, error);
        alert(`Error sending command to ${currentRemoteTV.name}`);
    }
}

async function fetchTVs() {
    try {
        // Quick path: fetch static TV list (fast, no network checks) and render
        const listRes = await fetch('/api/tvs');
        if (!listRes.ok) throw new Error('Failed to load TV list');

        const list = await listRes.json();

        // Initialize tvData with placeholders so UI renders immediately
        tvData = list.map(t => ({
            ip: t.ip,
            name: t.name || t.ip,
            mac: t.mac || '',
            online: false,
            ping_online: false,
            ws_online: false,
            token_verified: false,
            power_state: null,
        }));

        renderTVGrid();
        const loading = document.getElementById('loading');
        if (loading) loading.style.display = 'none';

        // Background: fetch enriched status and patch cards when ready
        try {
            const statusRes = await fetch('/api/tvs/status');
            if (statusRes.ok) {
                const statusList = await statusRes.json();
                // Merge status into tvData by IP
                statusList.forEach(s => {
                    const idx = tvData.findIndex(t => t.ip === s.ip);
                    if (idx >= 0) {
                        tvData[idx] = Object.assign({}, tvData[idx], s);
                    } else {
                        tvData.push(s);
                    }
                });
                renderTVGrid();
            } else {
                console.warn('Status endpoint returned non-OK');
            }
        } catch (err) {
            console.error('Error fetching TV statuses:', err);
        }

    } catch (error) {
        console.error('Error fetching TVs:', error);
        const grid = document.getElementById('tv-grid');
        grid.innerHTML = '<div class="col-span-5 text-center text-red-400 py-8">Error loading TVs</div>';
        const loading = document.getElementById('loading');
        if (loading) loading.style.display = 'none';
    }
}

function renderTVGrid() {
    const grid = document.getElementById('tv-grid');
    grid.innerHTML = '';

    // Sort TVs in specific order: T1-T5, M1-M5, B1-B5
    const sortedTVs = [...tvData].sort((a, b) => {
        const getOrder = (name) => {
            const match = name.match(/([TMB])(\d+)/i);
            if (!match) return 999; // Put unknown names at the end
            const letter = match[1].toUpperCase();
            const num = parseInt(match[2]);

            // T = 0-99, M = 100-199, B = 200-299
            if (letter === 'T') return num;
            if (letter === 'M') return 100 + num;
            if (letter === 'B') return 200 + num;
            return 999;
        };

        return getOrder(a.name) - getOrder(b.name);
    });

    sortedTVs.forEach(tv => {
        const card = document.createElement('div');
        const statusClass = tv.online ? 'online' : 'offline';

        let powerIcon = '';
        let powerColor = 'text-slate-600';
        let powerState = 'Unknown';
        if (tv.power_state) {
            const state = tv.power_state.toLowerCase();
            if (state === 'on') {
                powerIcon = '●';
                powerColor = 'text-green-400';
                powerState = 'On';
            } else if (state === 'standby') {
                powerIcon = '●';
                powerColor = 'text-orange-400';
                powerState = 'Standby';
            } else {
                powerIcon = '●';
                powerColor = 'text-red-400';
                powerState = 'Off';
            }
        } else {
            powerIcon = '○';
        }

        card.className = `tv-card ${statusClass}`;

        card.innerHTML = `
            <div class="tv-card-content">
                <div class="flex items-start justify-between">
                    <div class="text-lg font-bold text-slate-100">${tv.name}</div>
                    <div class="text-2xl ${powerColor}" title="${powerState}">${powerIcon}</div>
                </div>
                
                <div class="tv-screen">
                    <svg class="w-full h-full ${tv.online ? 'text-slate-600' : 'text-slate-800'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                </div>

                <div class="flex items-center gap-2">
                    <button onclick="togglePower('${tv.ip}', '${tv.name}')" 
                        class="flex-1 px-3 py-2 text-xs font-medium rounded-md text-slate-400 bg-transparent hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-500 transition-colors flex items-center justify-center">
                        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M18.36 6.64a9 9 0 1 1-12.73 0"/>
                            <line x1="12" x2="12" y1="2" y2="12"/>
                            <line x1="12" x2="12.01" y1="22" y2="18"/>
                        </svg>
                    </button>
                    <button onclick="openRemoteModal('${tv.ip}', '${tv.name}')" 
                        class="flex-1 px-3 py-2 text-xs font-medium rounded-md text-slate-400 bg-transparent hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-500 transition-colors flex items-center justify-center">
                        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <line x1="6" x2="10" y1="11" y2="11" stroke-width="3"/>
                            <line x1="8" x2="8" y1="9" y2="13" stroke-width="3"/>
                            <line x1="15" x2="15.01" y1="12" y2="12" stroke-width="3"/>
                            <line x1="18" x2="18.01" y1="10" y2="14" stroke-width="3"/>
                            <path stroke-width="3" d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16H14.17a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258A4 4 0 0 0 17.32 5z"/>
                        </svg>
                    </button>
                    <button onclick="window.location.href='/debug.html?ip=${encodeURIComponent(tv.ip)}'" 
                        class="flex-1 px-3 py-2 text-xs font-medium rounded-md text-slate-400 bg-transparent hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-500 transition-colors flex items-center justify-center">
                        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <polyline stroke-width="3" points="4,17 10,11 4,5"/>
                            <line stroke-width="3" x1="12" x2="20" y1="19" y2="19"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;

        grid.appendChild(card);
    });
}

async function togglePower(ip, name) {
    try {
        const res = await fetch(`/api/tvs/${encodeURIComponent(ip)}/power`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (res.ok) {
            const data = await res.json();
            console.log(`Power toggled for ${name}:`, data);
            // Refresh the TV data to show updated power state
            await fetchTVs();
        } else {
            const error = await res.text();
            console.error(`Failed to toggle power for ${name}:`, error);
            alert(`Failed to toggle power for ${name}`);
        }
    } catch (error) {
        console.error(`Error toggling power for ${name}:`, error);
        alert(`Error toggling power for ${name}`);
    }
}

async function refreshNow() {
    const btn = document.getElementById('btnRefresh');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="h-4 w-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refreshing...
        `;
    }

    await fetchTVs();

    if (btn) {
        btn.disabled = false;
        btn.innerHTML = `
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
        `;
    }
}

// Initial load and auto-refresh
fetchTVs();
setInterval(fetchTVs, 10000); // Refresh every 10 seconds
