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

        const token = tv.token_verified
            ? '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-900/30 text-blue-400 border border-blue-800">Verified</span>'
            : '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-900/30 text-yellow-400 border border-yellow-800">Unverified</span>'

        let powerState = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">Unknown</span>'
        if (tv.power_state) {
            const state = tv.power_state.toLowerCase()
            if (state === 'on') {
                powerState = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-800">On</span>'
            } else if (state === 'standby') {
                powerState = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-900/30 text-orange-400 border border-orange-800">Standby</span>'
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
            <td class="px-6 py-4 whitespace-nowrap text-center text-sm">${token}</td>
            <td class="px-6 py-4 whitespace-nowrap text-center text-sm">${powerState}</td>
        `
        tbody.appendChild(tr)
    }

    if (loading) loading.style.display = 'none'
}

fetchStatus()
setInterval(fetchStatus, 10000)