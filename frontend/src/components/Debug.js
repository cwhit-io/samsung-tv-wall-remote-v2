import React, { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';

function useLog() {
    const [entries, setEntries] = useState([]);
    const push = (type, message) => {
        const timestamp = new Date();
        setEntries(e => [...e, { type, message, timestamp }]);
    };
    const clear = () => setEntries([]);
    return { entries, push, clear };
}

const card = (label, children) => (
    <div className="bg-slate-800 rounded-lg p-4">
        <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">{label}</div>
        <div className="text-sm text-slate-100">{children}</div>
    </div>
);

const Debug = () => {
    const [searchParams] = useSearchParams();
    const [tvsData, setTvsData] = useState({});
    const [currentIP, setCurrentIP] = useState('');
    const [loadingTVs, setLoadingTVs] = useState(true);
    const [errorLoading, setErrorLoading] = useState(false);
    const { entries, push, clear } = useLog();
    const [buttonsDisabled, setButtonsDisabled] = useState(false);
    const logContainerRef = useRef(null);

    // Helper log shortcuts
    const log = (type, message) => push(type, message);

    useEffect(() => {
        const ip = searchParams.get('ip');
        loadTVs().then(() => {
            if (ip && tvsData[ip]) setCurrentIP(ip);
            // if ip param present but data not loaded yet, we'll set it after load
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        // scroll on new logs
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [entries]);

    async function loadTVs() {
        try {
            setLoadingTVs(true);
            const r = await fetch('/config/tvs.json');
            if (!r.ok) throw new Error('Failed to load config');
            const data = await r.json();
            setTvsData(data.tvs || {});
            log('success', `Loaded ${Object.keys(data.tvs || {}).length} TV(s) from configuration`);
            setErrorLoading(false);
        } catch (e) {
            log('error', `Failed to load TV configuration: ${e.message}`);
            setErrorLoading(true);
        } finally {
            setLoadingTVs(false);
        }
    }

    function selectTV(ip) {
        setCurrentIP(ip);
        const tv = tvsData[ip] || {};
        log('info', `Selected TV: ${tv.name || ip} (${ip})`);
    }

    async function wakeAllTVs() {
        log('info', 'Sending WOL to all TVs...');
        setButtonsDisabled(true);
        try {
            const r = await fetch('/api/tvs/wake-all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ port: 9 })
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            log('success', `WOL sent to ${data.success_count}/${data.total} TVs`);
        } catch (e) {
            log('error', `Failed to wake all TVs: ${e.message}`);
        } finally {
            setButtonsDisabled(false);
        }
    }

    // Simulated tests similar to static page
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    async function testPing(ip) {
        log('info', `Testing ping to ${ip}...`);
        try {
            const r = await fetch(`/api/debug/ping?ip=${encodeURIComponent(ip)}&force=true`);
            if (!r.ok) {
                log('error', `Ping check failed (HTTP ${r.status})`);
                return false;
            }
            const data = await r.json();
            if (data.ok) log('success', `✓ Ping successful`);
            else log('error', `✗ Ping failed: Host unreachable`);
            return !!data.ok;
        } catch (e) {
            log('error', `Ping error: ${e.message}`);
            return false;
        }
    }

    async function testPort(ip, port) {
        log('info', `Checking port ${port} on ${ip}...`);
        try {
            const r = await fetch(`/api/debug/port?ip=${encodeURIComponent(ip)}&port=${port}&force=true`);
            if (!r.ok) {
                log('error', `Port check failed (HTTP ${r.status})`);
                return false;
            }
            const data = await r.json();
            if (data.ok) log('success', `✓ Port ${port} is OPEN`);
            else log('warning', `✗ Port ${port} is CLOSED or filtered`);
            return !!data.ok;
        } catch (e) {
            log('error', `Port check error: ${e.message}`);
            return false;
        }
    }

    async function testSsdp(ip) {
        log('info', `Broadcasting SSDP discovery request...`);
        try {
            const r = await fetch(`/api/debug/ssdp?ip=${encodeURIComponent(ip)}&timeout=2`);
            if (!r.ok) {
                log('error', `SSDP discovery failed (HTTP ${r.status})`);
                return false;
            }
            const data = await r.json();
            if (data.ok) {
                log('success', `✓ SSDP response(s) received`);
                for (const res of data.results) {
                    log('info', `  From: ${res.from} - ST: ${res.headers.st || res.headers.server || 'unknown'}`);
                    if (res.headers.location) log('info', `    Location: ${res.headers.location}`);
                }
                return true;
            } else {
                log('warning', `✗ No SSDP responses (TV may be off or in deep sleep)`);
                return false;
            }
        } catch (e) {
            log('error', `SSDP error: ${e.message}`);
            return false;
        }
    }

    async function testWol(ip, mac) {
        log('info', `Sending WOL magic packet to ${mac}...`);
        log('info', `  Target IP: ${ip}`);
        try {
            const r = await fetch(`/api/debug/wake-and-wait`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ip, port: 9, wait_seconds: 30 })
            });
            if (!r.ok) {
                const text = await r.text();
                log('error', `WOL request failed (HTTP ${r.status}): ${text}`);
                return false;
            }
            const data = await r.json();
            log('success', `✓ WOL packet sent`);
            if (data.became_online) log('success', `✓ Device started responding after ${data.waited_seconds}s`);
            else log('warning', `✗ Device did not become reachable after ${data.waited_seconds}s`);
            return data.became_online;
        } catch (e) {
            log('error', `WOL error: ${e.message}`);
            return false;
        }
    }

    async function runTest(testType) {
        if (!currentIP) return log('error', 'Please select a TV first');
        setButtonsDisabled(true);
        try {
            switch (testType) {
                case 'ping':
                    await testPing(currentIP); break;
                case 'port8001':
                    await testPort(currentIP, 8001); break;
                case 'port8002':
                    await testPort(currentIP, 8002); break;
                case 'ssdp':
                    await testSsdp(currentIP); break;
                case 'wol':
                    await testWol(currentIP, (tvsData[currentIP] || {}).mac); break;
                case 'all':
                    log('info', '═══════════════════════════════════════');
                    log('info', 'Running comprehensive diagnostic suite...');
                    await testPing(currentIP);
                    await testPort(currentIP, 8001);
                    await testPort(currentIP, 8002);
                    await testSsdp(currentIP);
                    log('info', 'Diagnostic suite complete');
                    break;
            }
        } catch (e) {
            log('error', `Test failed: ${e.message}`);
        } finally {
            setButtonsDisabled(false);
        }
    }

    async function verifyToken() {
        if (!currentIP) return log('error', 'Please select a TV first');
        setButtonsDisabled(true);
        log('info', `Verifying token for ${currentIP}...`);
        try {
            const r = await fetch(`/api/tvs/${encodeURIComponent(currentIP)}/ws-check`);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            data.forEach(e => log(e.ok ? 'success' : 'warning', `${e.url} => ${e.ok}`));
        } catch (e) {
            log('error', `Token verification error: ${e.message}`);
        } finally { setButtonsDisabled(false); }
    }

    async function fetchFullStatus() {
        if (!currentIP) return log('error', 'Please select a TV first');
        setButtonsDisabled(true);
        log('info', `Fetching full status for ${currentIP}...`);
        try {
            const r = await fetch(`/api/tvs/${encodeURIComponent(currentIP)}/info`);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (data.ok) {
                log('success', `TV info: ${JSON.stringify(data.info)}`);
                // Update local tvsData display
                setTvsData(prev => ({ ...prev, [currentIP]: { ...(prev[currentIP] || {}), ...data.info } }));
            } else log('warning', `Could not fetch full status: ${data.error}`);
        } catch (e) {
            log('error', `Fetch full status error: ${e.message}`);
        } finally { setButtonsDisabled(false); }
    }

    async function sendWOL() {
        if (!currentIP) return log('error', 'Please select a TV first');
        setButtonsDisabled(true);
        log('info', `Sending WOL to ${currentIP}...`);
        try {
            const r = await fetch(`/api/tvs/${encodeURIComponent(currentIP)}/wake`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port: 9 })
            });
            if (r.ok) { log('success', `✓ WOL packet sent to ${(tvsData[currentIP] || {}).mac}`); }
            else { const text = await r.text(); log('error', `WOL failed (HTTP ${r.status}): ${text}`); }
        } catch (e) { log('error', `WOL error: ${e.message}`); }
        finally { setButtonsDisabled(false); }
    }

    async function togglePower() {
        if (!currentIP) return log('error', 'Please select a TV first');
        setButtonsDisabled(true);
        log('info', `Toggling power for ${currentIP}...`);
        try {
            const r = await fetch(`/api/tvs/${encodeURIComponent(currentIP)}/power`, { method: 'POST' });
            if (r.ok) { const data = await r.json(); log('success', `Power toggle successful: ${JSON.stringify(data)}`); }
            else { const text = await r.text(); log('error', `Power toggle failed (HTTP ${r.status}): ${text}`); }
        } catch (e) { log('error', `Power toggle error: ${e.message}`); }
        finally { setButtonsDisabled(false); }
    }

    async function requestNewToken() {
        if (!currentIP) return log('error', 'Please select a TV first');
        setButtonsDisabled(true);
        log('warning', `⚠️ CHECK YOUR TV SCREEN NOW! Look for pairing prompt and accept it`);
        try {
            const r = await fetch(`/api/tvs/${encodeURIComponent(currentIP)}/token`, { method: 'POST' });
            if (r.ok) {
                const data = await r.json();
                log('success', `✓ New token obtained: ${data.token}`);
                setTvsData(prev => ({ ...prev, [currentIP]: { ...(prev[currentIP] || {}), token: data.token } }));
            } else {
                const text = await r.text(); log('error', `Token request failed (HTTP ${r.status}): ${text}`);
            }
        } catch (e) { log('error', `Token request error: ${e.message}`); }
        finally { setButtonsDisabled(false); }
    }

    async function refreshAllTokens() {
        setButtonsDisabled(true);
        log('warning', '⚠️ CHECK ALL TV SCREENS! Each TV will show a pairing prompt that must be accepted');
        try {
            const r = await fetch('/api/tvs/refresh-all-tokens', { method: 'POST' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            log('info', `Total TVs: ${data.total}`);
            log('success', `✓ Success: ${data.success_count}`);
            log('error', `✗ Failed: ${data.failed_count}`);
            // reload TVs
            await loadTVs();
        } catch (e) { log('error', `Bulk refresh error: ${e.message}`); }
        finally { setButtonsDisabled(false); }
    }

    return (
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <div className="mb-6">
                <div className="flex items-center">
                    <svg className="h-8 w-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                    <h2 className="ml-3 text-2xl font-bold text-slate-100">Samsung TV Debug Tool</h2>
                </div>
                <p className="mt-1 text-sm text-slate-400">Network diagnostics and status monitoring</p>
            </div>

            {errorLoading && (
                <div className="mb-6 bg-red-900/30 border border-red-800 rounded-lg p-4">
                    <div className="flex"><svg className="h-5 w-5 text-red-500" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" /></svg>
                        <p className="ml-3 text-sm text-red-800">Failed to load TV configuration. Check that /config/tvs.json exists and is valid.</p></div>
                </div>
            )}

            <div className="bg-slate-900 rounded-lg shadow-xl border border-slate-800 p-6 mb-6">
                <h3 className="text-lg font-semibold text-slate-100 mb-4">Select TV</h3>
                <div className="mb-4">
                    <label htmlFor="tvSelect" className="block text-sm font-medium text-slate-300 mb-2">Choose a TV to debug:</label>
                    <select id="tvSelect" value={currentIP} onChange={e => selectTV(e.target.value)}
                        className="block w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm text-slate-100">
                        <option value="">{loadingTVs ? 'Loading TVs...' : '-- Select a TV --'}</option>
                        {Object.entries(tvsData).map(([ip, tv]) => (
                            <option key={ip} value={ip}>{tv.name} ({ip})</option>
                        ))}
                    </select>
                </div>

                <div id="tvInfo" className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {card('Name', (tvsData[currentIP] || {}).name || '-')}
                    {card('IP Address', currentIP || '-')}
                    {card('MAC Address', (tvsData[currentIP] || {}).mac || '-')}
                    {card('Model', (tvsData[currentIP] || {}).model || '-')}
                    {card('Token', <div className="text-sm font-mono text-slate-100 truncate">{(tvsData[currentIP] || {}).token || '-'}</div>)}
                    {card('Last Updated', (tvsData[currentIP] || {}).last_updated || '-')}
                </div>
            </div>

            <div className="bg-slate-900 rounded-lg shadow-xl border border-slate-800 p-6 mb-6">
                <h3 className="text-lg font-semibold text-slate-100 mb-4">Diagnostic Tests</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <button onClick={() => runTest('ping')} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">Ping Test</button>
                    <button onClick={() => runTest('port8001')} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">Check Port 8001</button>
                    <button onClick={() => runTest('port8002')} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">Check Port 8002</button>
                    <button onClick={() => runTest('ssdp')} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">SSDP Discovery</button>
                    <button onClick={sendWOL} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700">Wake (WOL)</button>
                    <button onClick={verifyToken} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">Verify Token</button>
                    <button onClick={fetchFullStatus} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">Get Full Status</button>
                    <button onClick={togglePower} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700">Toggle Power</button>
                    <button onClick={() => runTest('all')} disabled={buttonsDisabled} className="px-4 py-2 border border-slate-600 text-sm font-medium rounded-md text-slate-200 bg-slate-800 hover:bg-slate-700">Run All Tests</button>
                    <button onClick={wakeAllTVs} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700">Wake All TVs</button>
                </div>
            </div>

            <div className="bg-slate-900 rounded-lg shadow-xl border border-slate-800 p-6 mb-6">
                <h3 className="text-lg font-semibold text-slate-100 mb-4">Token Pairing</h3>
                <div className="mb-4">
                    <p className="text-sm text-slate-400 mb-4">Request a new authentication token from the TV. This will trigger a pairing prompt on the TV screen that you must accept.</p>
                    <div className="flex gap-3">
                        <button onClick={requestNewToken} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-orange-600 hover:bg-orange-700">Request New Token</button>
                        <button onClick={refreshAllTokens} disabled={buttonsDisabled} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700">Refresh All Tokens</button>
                    </div>
                </div>
            </div>

            <div className="bg-slate-900 rounded-lg shadow-xl border border-slate-800 p-6">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-slate-100">Debug Log</h3>
                    <button onClick={() => { clear(); log('info', 'Log cleared'); }} className="px-3 py-1 text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 rounded-md">Clear Log</button>
                </div>
                <div ref={logContainerRef} id="logContainer" className="bg-slate-950 rounded-lg p-4 font-mono text-sm max-h-96 overflow-y-auto border border-slate-800">
                    {entries.length === 0 && <div className="text-blue-400"><span className="text-slate-500">[--:--:--]</span> Waiting for TV selection...</div>}
                    {entries.map((e, idx) => (
                        <div key={idx} className={e.type === 'success' ? 'text-green-400' : e.type === 'error' ? 'text-red-400' : e.type === 'warning' ? 'text-yellow-400' : 'text-blue-400'}>
                            <span className="text-slate-500">[{e.timestamp.toLocaleTimeString()}]</span> {e.message}
                        </div>
                    ))}
                </div>
            </div>
        </main>
    );
};

export default Debug;