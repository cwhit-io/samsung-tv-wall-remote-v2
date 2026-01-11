let tvData = [];
let thumbnailRefreshInterval = null;
let lastThumbnailFetch = 0;
const THUMBNAIL_CACHE_MS = 60000; // 60 seconds
let currentLayer = 1;
let resolumeColumns = [];
let currentRemoteTV = null; // Track which TV the remote modal is controlling

async function refreshThumbnail(force = false, layer = null) {
    const now = Date.now();
    
    // Use provided layer or current layer
    const layerToUse = layer || currentLayer;
    
    // Check if we should skip due to cache (unless force refresh)
    if (!force && (now - lastThumbnailFetch) < THUMBNAIL_CACHE_MS) {
        return;
    }
    
    const img = document.getElementById('thumbnail-image');
    const loading = document.getElementById('thumbnail-loading');
    const error = document.getElementById('thumbnail-error');
    
    loading.classList.remove('hidden');
    error.classList.add('hidden');
    img.style.opacity = '0.5';
    
    try {
        // Add timestamp to prevent browser caching
        const timestamp = new Date().getTime();
        const response = await fetch(`/api/thumbnail?layer=${layerToUse}&t=${timestamp}`);
        
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
        
        // Update last fetch time
        lastThumbnailFetch = now;
        
    } catch (err) {
        console.error('Error loading thumbnail:', err);
        error.classList.remove('hidden');
        img.style.opacity = '1';
    } finally {
        loading.classList.add('hidden');
    }
}

async function loadResolumeColumns() {
    try {
        const res = await fetch('/api/resolume/columns');
        if (res.ok) {
            const data = await res.json();
            resolumeColumns = data.columns || [];
            
            const grid = document.getElementById('columns-grid');
            grid.innerHTML = '';
            
            // Filter out unused columns (Column #)
            const usedColumns = resolumeColumns.filter(col => !col.name.includes('Column #'));
            
            if (usedColumns.length === 0) {
                grid.innerHTML = '<div class="text-sm text-slate-400 col-span-2 text-center py-4">No columns found</div>';
                return;
            }
            
            usedColumns.forEach(column => {
                const btn = document.createElement('button');
                btn.onclick = () => triggerColumn(column.index);
                // Check if column is connected (handle both boolean and string values)
                const isConnected = column.connected === true || column.connected === 'Connected';
                const isEmpty = column.connected === 'Empty';
                
                let activeClass;
                if (isConnected) {
                    activeClass = 'bg-green-600 hover:bg-green-700 border-green-500';
                } else if (isEmpty) {
                    activeClass = 'bg-slate-700 hover:bg-slate-600 border-slate-600';
                } else {
                    activeClass = 'bg-blue-600 hover:bg-blue-700 border-blue-500';
                }
                
                btn.className = `px-3 py-2 text-sm font-medium rounded-md text-white ${activeClass} border transition-colors`;
                btn.textContent = column.name || `Column ${column.index}`;
                grid.appendChild(btn);
            });
        }
    } catch (err) {
        console.error('Error loading Resolume columns:', err);
        const grid = document.getElementById('columns-grid');
        grid.innerHTML = '<div class="text-sm text-red-400 col-span-2 text-center py-4">Error loading columns</div>';
    }
}

async function triggerColumn(columnIndex) {
    try {
        const res = await fetch(`/api/resolume/column/${columnIndex}/connect`, {
            method: 'POST'
        });
        
        if (res.ok) {
            console.log(`Triggered column ${columnIndex}`);
            // Refresh thumbnail and columns to show updated state
            await Promise.all([refreshThumbnail(true), loadResolumeColumns()]);
        } else {
            console.error('Failed to trigger column');
        }
    } catch (err) {
        console.error('Error triggering column:', err);
    }
}

async function loadResolumeData() {
    // Keep for backward compatibility, now just calls loadResolumeColumns
    await loadResolumeColumns();
}

async function triggerSelectedClip() {
    const clipSelect = document.getElementById('clip-select');
    const selectedClip = parseInt(clipSelect.value);
    
    if (isNaN(selectedClip) || selectedClip < 0) {
        alert('Please select a valid clip');
        return;
    }
    
    try {
        const res = await fetch(`/api/resolume/clip/${selectedClip}/connect`, {
            method: 'POST'
        });
        
        if (res.ok) {
            console.log(`Triggered clip ${selectedClip}`);
            await refreshThumbnail(true);
            // Reload clips to update active status
            await loadClipsForLayer(currentLayer);
        } else {
            alert('Failed to trigger clip');
        }
    } catch (err) {
        console.error('Error triggering clip:', err);
        alert('Error triggering clip');
    }
}

async function sendGlobalKey(key) {
    try {
        const res = await fetch('/api/tvs/broadcast-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key })
        });

        if (res.ok) {
            const data = await res.json();
            console.log(`Global key ${key} sent:`, data);
            // Optional: Show a brief toast notification
        } else {
            const error = await res.text();
            console.error(`Failed to send global key ${key}:`, error);
            alert(`Failed to send command to all TVs`);
        }
    } catch (error) {
        console.error(`Error sending global key ${key}:`, error);
        alert(`Error sending command to all TVs`);
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
                    <button onclick="openRemoteModal('${tv.ip}', '${tv.name}')" 
                        class="flex-1 px-3 py-2 text-xs font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 transition-colors">
                        Remote
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

// Initial load and auto-refresh
fetchTVs();
loadResolumeColumns();
refreshThumbnail(true); // Force initial load
setInterval(fetchTVs, 10000); // Refresh every 10 seconds
thumbnailRefreshInterval = setInterval(() => refreshThumbnail(false), 2000); // Check every 2 seconds but cache for 60s
