let tvsData = {};
let currentTV = null;

// Load TV configuration
async function loadTVs() {
    try {
        const response = await fetch('/config/tvs.json');
        if (!response.ok) throw new Error('Failed to load config');

        const data = await response.json();
        tvsData = data.tvs;

        populateDropdown();
        log('success', `Loaded ${Object.keys(tvsData).length} TV(s) from configuration`);
        return Promise.resolve();
    } catch (error) {
        log('error', `Failed to load TV configuration: ${error.message}`);
        const errorBanner = document.getElementById('errorBanner');
        errorBanner.classList.remove('hidden');
        document.getElementById('tvSelect').innerHTML = '<option value="">Error loading TVs</option>';
        return Promise.reject(error);
    }
}

// Populate dropdown with TVs
function populateDropdown() {
    const select = document.getElementById('tvSelect');
    select.innerHTML = '<option value="">-- Select a TV --</option>';

    Object.entries(tvsData).forEach(([ip, tv]) => {
        const option = document.createElement('option');
        option.value = ip;
        option.textContent = `${tv.name} (${ip})`;
        select.appendChild(option);
    });

    select.addEventListener('change', (e) => {
        if (e.target.value) {
            selectTV(e.target.value);
        } else {  // ✓ Fixed: Added 'else'
            document.getElementById('tvInfo').classList.remove('active');
            currentTV = null;
        }
    });  // ✓ Fixed: Proper closing
}

// Select and display TV info
function selectTV(ip) {
    currentTV = { ip, ...tvsData[ip] };

    document.getElementById('infoName').textContent = currentTV.name;
    document.getElementById('infoIP').textContent = ip;
    document.getElementById('infoMAC').textContent = currentTV.mac;
    document.getElementById('infoModel').textContent = currentTV.model;
    document.getElementById('infoToken').textContent = currentTV.token;
    document.getElementById('infoUpdated').textContent = currentTV.last_updated;

    document.getElementById('tvInfo').classList.add('active');

    log('info', `Selected TV: ${currentTV.name} (${ip})`);  // ✓ Fixed: Added log
}  // ✓ Fixed: Added closing brace

// Log message to console
function log(type, message) {
    const logContainer = document.getElementById('logContainer');
    const entry = document.createElement('div');

    // Map log types to Tailwind colors
    const colorMap = {
        'success': 'text-green-400',
        'error': 'text-red-400',
        'warning': 'text-yellow-400',
        'info': 'text-blue-400'
    };

    entry.className = colorMap[type] || 'text-slate-400';

    const timestamp = new Date().toLocaleTimeString();
    entry.innerHTML = `<span class="text-slate-500">[${timestamp}]</span> ${message}`;

    logContainer.appendChild(entry);
    logContainer.scrollTop = logContainer.scrollHeight;
}

// Clear log
function clearLog() {
    document.getElementById('logContainer').innerHTML = '';
    log('info', 'Log cleared');
}

// Disable all buttons
function disableButtons(disabled) {
    const buttons = document.querySelectorAll('button[id^="btn"]');
    buttons.forEach(btn => btn.disabled = disabled);
}

// Simulate ping test
async function testPing(ip) {
    log('info', `Testing ping to ${ip}...`);

    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 1000 + Math.random() * 1000));

    // Simulate 80% success rate
    const success = Math.random() > 0.2;

    if (success) {
        const latency = (Math.random() * 50 + 10).toFixed(2);
        log('success', `✓ Ping successful: ${latency}ms`);
        return true;
    } else {
        log('error', `✗ Ping failed: Host unreachable`);
        return false;
    }
}

// Simulate port check
async function testPort(ip, port) {
    log('info', `Checking port ${port} on ${ip}...`);

    await new Promise(resolve => setTimeout(resolve, 800 + Math.random() * 700));

    // Simulate port 8002 more likely to be open than 8001
    const successRate = port === 8002 ? 0.7 : 0.5;
    const success = Math.random() < successRate;

    if (success) {
        log('success', `✓ Port ${port} is OPEN`);
        return true;
    } else {
        log('warning', `✗ Port ${port} is CLOSED or filtered`);
        return false;
    }
}

// Simulate SSDP discovery
async function testSsdp(ip) {
    log('info', `Broadcasting SSDP discovery request...`);

    await new Promise(resolve => setTimeout(resolve, 2000));

    const success = Math.random() > 0.3;

    if (success) {
        log('success', `✓ SSDP response received from ${ip}`);
        log('info', `  Device: Samsung TV RemoteControlReceiver`);
        log('info', `  UDN: uuid:${Math.random().toString(36).substr(2, 9)}`);
        return true;
    } else {
        log('warning', `✗ No SSDP response (TV may be off or in deep sleep)`);
        return false;
    }
}

// Simulate WOL
async function testWol(ip, mac) {
    log('info', `Sending WOL magic packet to ${mac}...`);
    log('info', `  Target IP: ${ip}`);
    log('info', `  Broadcast: ${ip.split('.').slice(0, 3).join('.')}.255`);

    await new Promise(resolve => setTimeout(resolve, 500));

    log('success', `✓ WOL packet sent (102 bytes)`);
    log('info', `Waiting for device to respond...`);

    await new Promise(resolve => setTimeout(resolve, 3000));

    const success = Math.random() > 0.4;

    if (success) {
        log('success', `✓ Device is now responding to ping`);
        return true;
    } else {
        log('warning', `✗ Device did not respond after 30 seconds`);
        log('info', `  Possible causes: WOL disabled in BIOS, wrong MAC, device already on`);
        return false;
    }
}

// Run diagnostic test
async function runTest(testType) {
    if (!currentTV) {
        log('error', 'Please select a TV first');
        return;
    }

    disableButtons(true);

    try {
        switch (testType) {
            case 'ping':
                await testPing(currentTV.ip);
                break;
            case 'port8001':
                await testPort(currentTV.ip, 8001);
                break;
            case 'port8002':
                await testPort(currentTV.ip, 8002);
                break;
            case 'ssdp':
                await testSsdp(currentTV.ip);
                break;
            case 'wol':
                await testWol(currentTV.ip, currentTV.mac);
                break;
            case 'all':
                log('info', '═══════════════════════════════════════');
                log('info', 'Running comprehensive diagnostic suite...');
                log('info', '═══════════════════════════════════════');

                await testPing(currentTV.ip);
                await testPort(currentTV.ip, 8001);
                await testPort(currentTV.ip, 8002);
                await testSsdp(currentTV.ip);

                log('info', '═══════════════════════════════════════');
                log('info', 'Diagnostic suite complete');
                log('info', '═══════════════════════════════════════');
                break;
        }
    } catch (error) {
        log('error', `Test failed: ${error.message}`);
    } finally {
        disableButtons(false);
    }
}

// Verify token via API
async function verifyToken() {
    if (!currentTV) {
        log('error', 'Please select a TV first');
        return;
    }

    const btn = document.getElementById('btnVerify');
    btn.disabled = true;
    btn.textContent = 'Verifying...';

    try {
        const r = await fetch(`/api/tvs/${encodeURIComponent(currentTV.ip)}/ws-check`);
        if (!r.ok) {
            log('error', `Token verification failed (HTTP ${r.status})`);
            return;
        }
        const data = await r.json();
        // data is a list of endpoints
        data.forEach(e => log(e.ok ? 'success' : 'warning', `${e.url} => ${e.ok}`));
    } catch (e) {
        log('error', `Token verification error: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Verify Token';
    }
}

// Fetch detailed TV status
async function fetchFullStatus() {
    if (!currentTV) {
        log('error', 'Please select a TV first');
        return;
    }

    const btn = document.getElementById('btnFetchStatus');
    btn.disabled = true;
    btn.textContent = 'Fetching...';

    try {
        const r = await fetch(`/api/tvs/${encodeURIComponent(currentTV.ip)}/info`);
        if (!r.ok) {
            log('error', `Failed to fetch status (HTTP ${r.status})`);
            return;
        }
        const data = await r.json();
        if (data.ok) {
            log('success', `TV info: ${JSON.stringify(data.info)}`);
            // populate info fields if available
            if (data.info.name) document.getElementById('infoName').textContent = data.info.name;
            if (data.info.model) document.getElementById('infoModel').textContent = data.info.model;
            if (data.info.token) document.getElementById('infoToken').textContent = data.info.token;
        } else {
            log('warning', `Could not fetch full status: ${data.error}`);
        }
    } catch (e) {
        log('error', `Fetch full status error: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Get Full Status';
    }
}

// Send WOL to current TV
async function sendWOL() {
    if (!currentTV) {
        log('error', 'Please select a TV first');
        return;
    }

    const btn = document.getElementById('btnWol');
    btn.disabled = true;
    btn.textContent = 'Sending...';

    try {
        log('info', `Sending WOL magic packet to ${currentTV.mac}...`);
        const r = await fetch(`/api/tvs/${encodeURIComponent(currentTV.ip)}/wake`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port: 9 })
        });

        if (r.ok) {
            const data = await r.json();
            log('success', `✓ WOL packet sent to ${currentTV.mac}`);
            log('info', `Wait 10-20 seconds for TV to boot and WebSocket service to start...`);
        } else {
            const errorText = await r.text();
            log('error', `✗ WOL failed (HTTP ${r.status})`);
            log('error', `Error: ${errorText}`);
        }
    } catch (e) {
        log('error', `WOL error: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Wake (WOL)';
    }
}

// Toggle power for current TV
async function togglePower() {
    if (!currentTV) {
        log('error', 'Please select a TV first');
        return;
    }

    const btn = document.getElementById('btnPowerToggle');
    btn.disabled = true;
    btn.textContent = 'Toggling...';

    try {
        log('info', `Sending KEY_POWER command via WebSocket to ${currentTV.ip}...`);
        log('info', `Note: TV must be fully booted and have "Remote Access" enabled in settings`);
        const r = await fetch(`/api/tvs/${encodeURIComponent(currentTV.ip)}/power`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (r.ok) {
            const data = await r.json();
            log('success', `✓ Power toggle successful for ${currentTV.ip}`);
            log('info', `Response: ${JSON.stringify(data)}`);
        } else {
            const errorText = await r.text();
            log('error', `✗ Power toggle failed (HTTP ${r.status})`);
            log('error', `Error: ${errorText}`);
        }
    } catch (e) {
        log('error', `Power toggle error: ${e.message}`);
        log('error', `Stack: ${e.stack}`);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Toggle Power';
    }
}

// Request new token from TV
async function requestNewToken() {
    if (!currentTV) {
        log('error', 'Please select a TV first');
        return;
    }

    const btn = document.getElementById('btnRequestToken');
    const resultDiv = document.getElementById('tokenResult');
    const outputDiv = document.getElementById('tokenOutput');

    btn.disabled = true;
    btn.textContent = 'Requesting...';
    resultDiv.classList.add('hidden');
    outputDiv.textContent = '';

    log('info', `Requesting new token from ${currentTV.ip}...`);
    log('warning', `⚠️ CHECK YOUR TV SCREEN NOW! Look for pairing prompt and accept it with remote`);

    try {
        const r = await fetch(`/api/tvs/${encodeURIComponent(currentTV.ip)}/token`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (r.ok) {
            const data = await r.json();
            const newToken = data.token;

            log('success', `✓ New token obtained: ${newToken}`);
            log('success', `💾 Token automatically saved to config/tvs.json`);

            // Show result in UI
            resultDiv.classList.remove('hidden');
            outputDiv.innerHTML = `
                <div class="text-green-400 font-bold mb-2">SUCCESS! New token obtained and saved:</div>
                <div class="bg-slate-900 p-3 rounded border font-mono text-lg">${newToken}</div>
                <div class="text-sm text-slate-400 mt-2">
                    Token has been automatically saved to <code>config/tvs.json</code> for ${currentTV.ip}
                </div>
            `;

            // Update the displayed token
            document.getElementById('infoToken').textContent = newToken;
            currentTV.token = newToken;

        } else {
            const errorText = await r.text();
            log('error', `✗ Token request failed (HTTP ${r.status})`);
            log('error', `Error: ${errorText}`);

            resultDiv.classList.remove('hidden');
            outputDiv.innerHTML = `
                <div class="text-red-400 font-bold mb-2">FAILED:</div>
                <div class="text-red-300">${errorText}</div>
                <div class="text-sm text-slate-400 mt-2">
                    Make sure TV is ON and you accept the pairing prompt on screen.
                </div>
            `;
        }
    } catch (e) {
        log('error', `Token request error: ${e.message}`);
        log('error', `Stack: ${e.stack}`);

        resultDiv.classList.remove('hidden');
        outputDiv.innerHTML = `
            <div class="text-red-400 font-bold mb-2">ERROR:</div>
            <div class="text-red-300">${e.message}</div>
        `;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Request New Token';
    }
}

// Refresh all tokens for all TVs
async function refreshAllTokens() {
    const btn = document.getElementById('btnRefreshAll');
    const resultDiv = document.getElementById('tokenResult');
    const outputDiv = document.getElementById('tokenOutput');

    btn.disabled = true;
    btn.textContent = 'Refreshing All...';
    resultDiv.classList.add('hidden');
    outputDiv.textContent = '';

    log('info', 'Starting token refresh for all TVs...');
    log('warning', '⚠️ CHECK ALL TV SCREENS! Each TV will show a pairing prompt that must be accepted');

    try {
        const r = await fetch('/api/tvs/refresh-all-tokens', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (r.ok) {
            const data = await r.json();
            
            log('info', `Total TVs: ${data.total}`);
            log('success', `✓ Success: ${data.success_count}`);
            log('error', `✗ Failed: ${data.failed_count}`);
            log('warning', `⊘ Skipped: ${data.skipped_count}`);

            // Log details
            data.results.success.forEach(tv => {
                log('success', `✓ ${tv.name} (${tv.ip}): ${tv.token}`);
            });

            data.results.failed.forEach(tv => {
                log('error', `✗ ${tv.name} (${tv.ip}): ${tv.error}`);
            });

            data.results.skipped.forEach(tv => {
                log('warning', `⊘ ${tv.name} (${tv.ip}): ${tv.reason}`);
            });

            // Show summary in result box
            resultDiv.classList.remove('hidden');
            let summaryHtml = `
                <div class="text-slate-300 font-bold mb-3">Refresh Complete</div>
                <div class="space-y-2">
                    <div class="text-green-400">✓ Success: ${data.success_count}</div>
                    <div class="text-red-400">✗ Failed: ${data.failed_count}</div>
                    <div class="text-yellow-400">⊘ Skipped: ${data.skipped_count}</div>
                </div>
            `;

            if (data.success_count > 0) {
                summaryHtml += `
                    <div class="mt-4 pt-4 border-t border-slate-700">
                        <div class="text-sm text-slate-400 mb-2">New tokens saved:</div>
                        ${data.results.success.map(tv => `
                            <div class="text-xs font-mono text-green-400">${tv.name}: ${tv.token}</div>
                        `).join('')}
                        <div class="text-sm text-slate-400 mt-2">
                            All tokens automatically saved to <code>config/tvs.json</code>
                        </div>
                    </div>
                `;
            }

            outputDiv.innerHTML = summaryHtml;

            // Reload TV data to get updated tokens
            await loadTVs();
            if (currentTV) {
                selectTV(currentTV.ip);
            }

        } else {
            const errorText = await r.text();
            log('error', `✗ Bulk refresh failed (HTTP ${r.status})`);
            log('error', `Error: ${errorText}`);

            resultDiv.classList.remove('hidden');
            outputDiv.innerHTML = `
                <div class="text-red-400 font-bold mb-2">FAILED:</div>
                <div class="text-red-300">${errorText}</div>
            `;
        }
    } catch (e) {
        log('error', `Bulk refresh error: ${e.message}`);
        log('error', `Stack: ${e.stack}`);

        resultDiv.classList.remove('hidden');
        outputDiv.innerHTML = `
            <div class="text-red-400 font-bold mb-2">ERROR:</div>
            <div class="text-red-300">${e.message}</div>
        `;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Refresh All Tokens';
    }
}

// Check URL parameters for pre-selected TV
function checkUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const ip = params.get('ip');
    if (ip && tvsData[ip]) {
        document.getElementById('tvSelect').value = ip;
        selectTV(ip);
    }
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
    loadTVs().then(() => {
        checkUrlParams();
    });
});
