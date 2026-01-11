async function fetchStatus() {
    const res = await fetch('/api/tvs/status')
    const tbody = document.querySelector('#tv-table tbody')
    const loading = document.querySelector('#loading')

    if (!res.ok) {
        tbody.innerHTML = '<tr><td colspan="8" class="px-6 py-4 text-center text-red-400">Error fetching status</td></tr>'
        if (loading) loading.style.display = 'none'
        return
    }

    const data = await res.json()
    tbody.innerHTML = ''

    for (const tv of data) {
        const tr = document.createElement('tr')
        tr.className = 'hover:bg-slate-800/50 transition-colors cursor-pointer'
        tr.onclick = () => window.location.href = `/debug.html?ip=${encodeURIComponent(tv.ip)}`

        const statusOnline = tv.online
            ? '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-800">Online</span>'
            : '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400 border border-red-800">Offline</span>'

        const ws = tv.ws_online
            ? '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-800">Open</span>'
            : '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">Closed</span>'

        let powerState = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">Unknown</span>'
        if (tv.power_state) {
            const state = tv.power_state.toLowerCase()
            if (state === 'on') {
                powerState = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-800">On</span>'
            } else if (state === 'standby') {
                powerState = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-900/30 text-orange-400 border border-orange-800">Standby</span>'
            } else if (state === 'off') {
                powerState = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400 border border-red-800">Off</span>'
            } else {
                powerState = `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">${tv.power_state}</span>`
            }
        }

        tr.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-slate-200">${tv.ip}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-slate-100">${tv.name}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-slate-400">${tv.mac}</td>
            <td class="px-6 py-4 whitespace-nowrap text-center text-sm">${statusOnline}</td>
            <td class="px-6 py-4 whitespace-nowrap text-center text-sm">${ws}</td>
            <td class="px-6 py-4 whitespace-nowrap text-center text-sm">${powerState}</td>
        `
        tbody.appendChild(tr)
    }

    if (loading) loading.style.display = 'none'
}

// Manual refresh function
async function refreshNow() {
    const btn = document.getElementById('btnRefresh')
    if (btn) {
        btn.disabled = true
        btn.innerHTML = `
            <svg class="h-4 w-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refreshing...
        `
    }
    
    await fetchStatus()
    
    if (btn) {
        btn.disabled = false
        btn.innerHTML = `
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
        `
    }
}

fetchStatus()
setInterval(fetchStatus, 10000)