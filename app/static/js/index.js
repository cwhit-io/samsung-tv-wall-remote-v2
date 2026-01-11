let tvData = [];
let thumbnailRefreshInterval = null;

async function refreshThumbnail() {
    const img = document.getElementById('thumbnail-image');
    const loading = document.getElementById('thumbnail-loading');
    const error = document.getElementById('thumbnail-error');
    
    loading.classList.remove('hidden');
    error.classList.add('hidden');
    img.style.opacity = '0.5';
    
    try {
        // Add timestamp to prevent caching
        const timestamp = new Date().getTime();
        const response = await fetch(`/api/thumbnail?t=${timestamp}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        
        // Revoke old object URL if it exists
        if (img.src && img.src.startsWith('blob:')) {
            URL.revokeObjectURL(img.src);
        }
        
        img.src = objectUrl;
        img.style.opacity = '1';
        loading.classList.add('hidden');
        
    } catch (err) {
        console.error('Error loading thumbnail:', err);
        error.classList.remove('hidden');
        img.style.opacity = '1';
    } finally {
        loading.classList.add('hidden');
    }
}

async function fetchTVs() {
    try {
        const res = await fetch('/api/tvs/status');
        if (!res.ok) throw new Error('Failed to fetch TVs');
        
        tvData = await res.json();
        renderTVGrid();
        
        const loading = document.getElementById('loading');
        if (loading) loading.style.display = 'none';
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
                        class="flex-1 px-3 py-2 text-xs font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-colors">
                        Power
                    </button>
                    <button onclick="window.location.href='/debug.html?ip=${encodeURIComponent(tv.ip)}'" 
                        class="flex-1 px-3 py-2 text-xs font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors">
                        Debug
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

async function toggleAllPower() {
    const btn = document.getElementById('btnTogglePower');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="h-4 w-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            Toggling...
        `;
    }
    
    try {
        const res = await fetch('/api/tvs/broadcast-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: 'KEY_POWER' })
        });

        if (res.ok) {
            const data = await res.json();
            console.log('Power toggle broadcast result:', data);
            // Wait a moment for TVs to process command, then refresh
            await new Promise(resolve => setTimeout(resolve, 2000));
            await fetchTVs();
        } else {
            const error = await res.text();
            console.error('Failed to broadcast power toggle:', error);
            alert('Failed to toggle power on all TVs');
        }
    } catch (error) {
        console.error('Error broadcasting power toggle:', error);
        alert('Error toggling power on all TVs');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Toggle All Power
            `;
        }
    }
}

// Initial load and auto-refresh
fetchTVs();
refreshThumbnail();
setInterval(fetchTVs, 10000); // Refresh every 10 seconds
thumbnailRefreshInterval = setInterval(refreshThumbnail, 2000); // Refresh thumbnail every 2 seconds
