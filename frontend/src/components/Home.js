import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

const THUMBNAIL_CACHE_MS = 60000;

function Toast({ toast }) {
    if (!toast) return null;
    const bg = toast.type === 'success' ? 'bg-green-600' : toast.type === 'error' ? 'bg-red-600' : 'bg-blue-600';
    return (
        <div className={`fixed top-20 right-4 px-6 py-3 rounded-lg shadow-lg text-white z-50 transition-opacity duration-300 ${bg}`}>
            {toast.message}
        </div>
    );
}

const Home = () => {
    const [tvData, setTvData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const [toast, setToast] = useState(null);
    const toastTimerRef = useRef(null);

    const [globalRemoteOpen, setGlobalRemoteOpen] = useState(false);
    const [remoteOpen, setRemoteOpen] = useState(false);
    const [remoteTV, setRemoteTV] = useState(null);
    const [remoteBusy, setRemoteBusy] = useState(false);

    const [currentLayer, setCurrentLayer] = useState(1);
    const [columns, setColumns] = useState([]);
    const [columnsError, setColumnsError] = useState(null);
    const [activeColumnIndex, setActiveColumnIndex] = useState(null);
    const [thumbnailUrl, setThumbnailUrl] = useState('');
    const [thumbnailLoading, setThumbnailLoading] = useState(false);
    const [thumbnailError, setThumbnailError] = useState(false);
    const lastThumbnailFetchRef = useRef(0);
    const currentObjectUrlRef = useRef(null);

    function showToast(message, type = 'info') {
        setToast({ message, type });
        if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
        toastTimerRef.current = setTimeout(() => setToast(null), 3000);
    }

    const fetchTVs = async () => {
        setError(null);
        try {
            const res = await fetch('/api/tvs/status');
            if (!res.ok) throw new Error(`Failed to fetch TVs (HTTP ${res.status})`);
            const data = await res.json();
            setTvData(data);
        } catch (err) {
            console.error('Error fetching TVs:', err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTVs();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const sortedTVs = useMemo(() => {
        const tvs = [...tvData];
        const getOrder = (name) => {
            const match = String(name || '').match(/([TMB])(\d+)/i);
            if (!match) return 999;
            const letter = match[1].toUpperCase();
            const num = parseInt(match[2], 10);
            if (letter === 'T') return num;
            if (letter === 'M') return 100 + num;
            if (letter === 'B') return 200 + num;
            return 999;
        };
        return tvs.sort((a, b) => getOrder(a.name) - getOrder(b.name));
    }, [tvData]);

    const togglePower = async (ip, name) => {
        try {
            const res = await fetch(`/api/tvs/${encodeURIComponent(ip)}/power`, { method: 'POST' });
            if (res.ok) {
                showToast(`✓ Power toggled: ${name}`, 'success');
                fetchTVs();
            } else {
                const txt = await res.text().catch(() => '');
                showToast(`Failed to toggle power: ${name}`, 'error');
                console.error(txt);
            }
        } catch (err) {
            showToast(`Error toggling power: ${name}`, 'error');
        }
    };

    const openRemoteModal = (ip, name) => {
        setRemoteTV({ ip, name });
        setRemoteOpen(true);
    };

    const closeRemoteModal = () => {
        setRemoteOpen(false);
        setRemoteTV(null);
    };

    async function sendGlobalKey(key) {
        if (remoteBusy) return;
        setRemoteBusy(true);
        try {
            showToast('Sending command to all TVs...', 'info');
            const res = await fetch('/api/tvs/broadcast-key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key })
            });
            if (!res.ok) {
                const txt = await res.text().catch(() => '');
                throw new Error(`HTTP ${res.status}: ${txt}`);
            }
            const data = await res.json();
            showToast(`✓ Command sent to ${data.success_count}/${data.total} TVs`, 'success');
        } catch (err) {
            console.error(err);
            showToast('Failed to send command to all TVs', 'error');
        } finally {
            setRemoteBusy(false);
        }
    }

    async function sendIndividualKey(key) {
        if (!remoteTV || remoteBusy) return;
        setRemoteBusy(true);
        try {
            const res = await fetch(`/api/tvs/${encodeURIComponent(remoteTV.ip)}/send-key`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key })
            });
            if (!res.ok) {
                const txt = await res.text().catch(() => '');
                throw new Error(`HTTP ${res.status}: ${txt}`);
            }
            showToast(`✓ Sent ${key} to ${remoteTV.name}`, 'success');
        } catch (err) {
            console.error(err);
            showToast(`Failed to send ${key}`, 'error');
        } finally {
            setRemoteBusy(false);
        }
    }

    async function refreshThumbnail(force = false, layer = null) {
        const now = Date.now();
        const layerToUse = layer || currentLayer;

        if (!force && (now - lastThumbnailFetchRef.current) < THUMBNAIL_CACHE_MS) {
            return;
        }

        setThumbnailLoading(true);
        setThumbnailError(false);
        try {
            const timestamp = new Date().getTime();
            const response = await fetch(`/api/thumbnail?layer=${layerToUse}&t=${timestamp}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);

            if (currentObjectUrlRef.current) {
                URL.revokeObjectURL(currentObjectUrlRef.current);
            }
            currentObjectUrlRef.current = objectUrl;

            setThumbnailUrl(objectUrl);
            lastThumbnailFetchRef.current = now;
        } catch (err) {
            console.error('Error loading thumbnail:', err);
            setThumbnailError(true);
        } finally {
            setThumbnailLoading(false);
        }
    }

    async function loadResolumeColumns(layer = currentLayer) {
        setColumnsError(null);
        try {
            const res = await fetch(`/api/resolume/columns?layer=${encodeURIComponent(layer)}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const nextColumns = data.columns || [];
            setColumns(nextColumns);

            // If we don't yet have an active column for this layer, pick a sensible default.
            // Resolume can report multiple columns as "Connected", so we just pick the first.
            if (activeColumnIndex == null) {
                const firstConnected = nextColumns.find(c => c && (c.connected === true || c.connected === 'Connected' || c.connected === 2));
                if (firstConnected?.index != null) setActiveColumnIndex(firstConnected.index);
            }
        } catch (err) {
            console.error('Error loading Resolume columns:', err);
            setColumnsError('Error loading columns');
            setColumns([]);
        }
    }

    async function triggerColumn(columnIndex) {
        try {
            const res = await fetch(
                `/api/resolume/column/${columnIndex}/connect?layer=${encodeURIComponent(currentLayer)}`,
                { method: 'POST' }
            );
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            setActiveColumnIndex(columnIndex);
            await Promise.all([refreshThumbnail(true), loadResolumeColumns(currentLayer)]);
        } catch (err) {
            console.error('Error triggering column:', err);
            showToast('Failed to trigger column', 'error');
        }
    }

    const usedColumns = useMemo(() => {
        return (columns || []).filter(col => !String(col.name || '').includes('Column #'));
    }, [columns]);

    useEffect(() => {
        loadResolumeColumns(currentLayer);
        refreshThumbnail(true, currentLayer);
        const id = setInterval(() => refreshThumbnail(false), 10000);
        return () => {
            clearInterval(id);
            if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
            if (currentObjectUrlRef.current) URL.revokeObjectURL(currentObjectUrlRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        loadResolumeColumns(currentLayer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentLayer]);

    return (
        <>
            <Toast toast={toast} />

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="mb-6 flex items-center justify-between">
                    <h2 className="text-2xl font-bold text-slate-100">TV Grid</h2>
                    <div className="flex items-center gap-3">
                        <button onClick={() => setGlobalRemoteOpen(true)}
                            className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 transition-colors flex items-center gap-2">
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                                    d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                            Global Remote
                        </button>
                        <button onClick={() => { setLoading(true); fetchTVs(); }} id="btnRefresh"
                            className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                            disabled={loading}
                        >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            Refresh
                        </button>
                    </div>
                </div>

                {error && (
                    <div className="mb-6 bg-red-900/30 border border-red-800 rounded-lg p-4">
                        <p className="text-red-400 text-sm">{error}</p>
                    </div>
                )}

                {loading ? (
                    <div className="text-center py-16">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
                        <p className="mt-4 text-sm text-slate-400">Loading TVs...</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-5 gap-4" id="tv-grid">
                        {sortedTVs.map(tv => {
                            const wsOk = tv.ws_online === true;

                            let powerLabel = 'Unknown';
                            let powerBadgeClass = 'unknown';
                            if (tv.power_state) {
                                const state = String(tv.power_state).toLowerCase();
                                if (state === 'on') {
                                    powerLabel = 'On';
                                    powerBadgeClass = 'on';
                                } else if (state === 'standby') {
                                    powerLabel = 'Standby';
                                    powerBadgeClass = 'standby';
                                } else {
                                    powerLabel = 'Off';
                                    powerBadgeClass = 'off';
                                }
                            }

                            return (
                                <div key={tv.ip} className={`tv-card ${tv.online ? 'online' : 'offline'}`}>
                                    <div className="tv-card-content">
                                        <div className={`tv-ws-dot ${wsOk ? 'ok' : 'bad'}`} title={`WebSocket: ${wsOk ? 'OK' : 'Down'}`} />

                                        <div className="tv-tile-top">
                                            <div className="tv-title" title={tv.name}>{tv.name}</div>
                                            <div className={`tv-power-badge ${powerBadgeClass}`} title={`Power: ${powerLabel}`}>
                                                {powerLabel}
                                            </div>
                                        </div>

                                        <div className="tv-actions-overlay" aria-label="TV actions">
                                            <button
                                                type="button"
                                                className="tv-action-btn"
                                                onClick={() => togglePower(tv.ip, tv.name)}
                                                title="Power"
                                            >
                                                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18.36 6.64a9 9 0 1 1-12.73 0" />
                                                    <line x1="12" x2="12" y1="2" y2="12" />
                                                </svg>
                                            </button>

                                            <button
                                                type="button"
                                                className="tv-action-btn"
                                                onClick={() => openRemoteModal(tv.ip, tv.name)}
                                                title="Remote"
                                            >
                                                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <line x1="6" x2="10" y1="11" y2="11" strokeWidth="2" />
                                                    <line x1="8" x2="8" y1="9" y2="13" strokeWidth="2" />
                                                    <line x1="15" x2="15.01" y1="12" y2="12" strokeWidth="2" />
                                                    <line x1="18" x2="18.01" y1="10" y2="14" strokeWidth="2" />
                                                    <path strokeWidth="2" d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16H14.17a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258A4 4 0 0 0 17.32 5z" />
                                                </svg>
                                            </button>

                                            <Link
                                                to={`/debug?ip=${encodeURIComponent(tv.ip)}`}
                                                className="tv-action-btn"
                                                title="Debug"
                                            >
                                                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <polyline strokeWidth="2" points="4,17 10,11 4,5" />
                                                    <line strokeWidth="2" x1="12" x2="20" y1="19" y2="19" />
                                                </svg>
                                            </Link>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Resolume Section */}
                <div className="mt-8">
                    <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
                        <div className="flex items-center justify-between mb-3">
                            <h3 className="text-lg font-semibold text-slate-100">Resolume Control</h3>
                            <button onClick={loadResolumeColumns}
                                className="px-3 py-1 text-xs font-medium rounded text-white bg-slate-700 hover:bg-slate-600 transition-colors">
                                Refresh
                            </button>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            <div>
                                <div className="text-xs font-semibold text-slate-300 mb-2">Current Output (Layer <span>{currentLayer}</span>)</div>
                                <div className="relative bg-slate-950 rounded overflow-hidden" style={{ aspectRatio: '16/9' }}>
                                    <img
                                        src={thumbnailUrl}
                                        className="w-full h-full object-contain"
                                        alt="Resolume Thumbnail"
                                        style={{ opacity: thumbnailLoading ? 0.5 : 1 }}
                                    />
                                    {thumbnailLoading && (
                                        <div className="absolute inset-0 flex items-center justify-center">
                                            <div className="text-slate-500 text-xs">Loading...</div>
                                        </div>
                                    )}
                                    {thumbnailError && (
                                        <div className="absolute inset-0 flex items-center justify-center">
                                            <div className="text-red-400 text-xs">Failed to load</div>
                                        </div>
                                    )}
                                </div>
                                <div className="mt-3 flex items-center gap-2">
                                    <button onClick={() => refreshThumbnail(true)}
                                        className="px-3 py-1 text-xs font-medium rounded text-white bg-blue-600 hover:bg-blue-700 transition-colors">
                                        Refresh Thumbnail
                                    </button>
                                    <label className="text-xs text-slate-400">Layer</label>
                                    <input
                                        type="number"
                                        min={1}
                                        value={currentLayer}
                                        onChange={(e) => {
                                            const v = parseInt(e.target.value || '1', 10);
                                            setCurrentLayer(v);
                                            refreshThumbnail(true, v);
                                        }}
                                        className="w-20 px-2 py-1 text-xs bg-slate-800 border border-slate-700 rounded text-slate-100"
                                    />
                                </div>
                            </div>

                            <div className="space-y-3">
                                <div>
                                    <label className="text-xs font-semibold text-slate-300 mb-2 block">Columns</label>
                                    <div className="grid grid-cols-2 gap-2 max-h-80 overflow-y-auto">
                                        {columnsError && (
                                            <div className="text-sm text-red-400 col-span-2 text-center py-4">{columnsError}</div>
                                        )}
                                        {!columnsError && usedColumns.length === 0 && (
                                            <div className="text-sm text-slate-400 col-span-2 text-center py-4">No columns found</div>
                                        )}

                                        {usedColumns.map((column) => {
                                            const isActive = column.index === activeColumnIndex;
                                            const connected = column.connected === true || column.connected === 'Connected' || column.connected === 2;
                                            const empty = column.connected === 'Empty';
                                            const activeClass = isActive
                                                ? 'bg-green-600 hover:bg-green-700 border-green-500'
                                                : empty
                                                    ? 'bg-slate-700 hover:bg-slate-600 border-slate-600'
                                                    : connected
                                                        ? 'bg-blue-700 hover:bg-blue-800 border-blue-600'
                                                        : 'bg-blue-600 hover:bg-blue-700 border-blue-500';
                                            return (
                                                <button
                                                    key={column.index}
                                                    onClick={() => triggerColumn(column.index)}
                                                    className={`px-3 py-2 text-sm font-medium rounded-md text-white ${activeClass} border transition-colors`}
                                                >
                                                    {column.name || `Column ${column.index}`}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>

            {/* Global Remote Modal */}
            {globalRemoteOpen && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={() => setGlobalRemoteOpen(false)}>
                    <div className="bg-gradient-to-b from-slate-800 to-slate-900 rounded-2xl shadow-2xl max-w-sm w-full mx-4 border border-slate-700" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-between p-5 border-b border-slate-700 bg-slate-800/50 rounded-t-2xl">
                            <h3 className="text-lg font-semibold text-slate-100">Global Remote</h3>
                            <button onClick={() => setGlobalRemoteOpen(false)} className="text-slate-400 hover:text-slate-100 transition-colors">
                                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>

                        <div className="p-6">
                            <div className="text-xs text-slate-400 mb-4 text-center">Controls all TVs simultaneously</div>

                            <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_POWER')} className="remote-btn-lg bg-red-600 hover:bg-red-700 w-full mb-4">
                                <svg className="h-5 w-5 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728m-9.9-2.829a5 5 0 010-7.07m7.072 0a5 5 0 010 7.07M13 12a1 1 0 11-2 0 1 1 0 012 0z" />
                                </svg>
                                <span className="ml-2">Power</span>
                            </button>

                            <div className="grid grid-cols-3 gap-3 mb-4">
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_VOLDOWN')} className="remote-btn-md bg-blue-600 hover:bg-blue-700">Vol−</button>
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_MUTE')} className="remote-btn-md bg-orange-600 hover:bg-orange-700">
                                    <svg className="h-5 w-5 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" clipRule="evenodd" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
                                    </svg>
                                </button>
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_VOLUP')} className="remote-btn-md bg-blue-600 hover:bg-blue-700">Vol+</button>
                            </div>

                            <div className="bg-slate-800/50 rounded-xl p-4 mb-4">
                                <div className="grid grid-cols-3 gap-2">
                                    <div></div>
                                    <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_UP')} className="remote-btn-nav bg-slate-600 hover:bg-slate-700">
                                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" />
                                        </svg>
                                    </button>
                                    <div></div>
                                    <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_LEFT')} className="remote-btn-nav bg-slate-600 hover:bg-slate-700">
                                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" />
                                        </svg>
                                    </button>
                                    <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_ENTER')} className="remote-btn-ok bg-green-600 hover:bg-green-700">OK</button>
                                    <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_RIGHT')} className="remote-btn-nav bg-slate-600 hover:bg-slate-700">
                                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                                        </svg>
                                    </button>
                                    <div></div>
                                    <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_DOWN')} className="remote-btn-nav bg-slate-600 hover:bg-slate-700">
                                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
                                        </svg>
                                    </button>
                                    <div></div>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-3 mb-4">
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_RETURN')} className="remote-btn-md bg-slate-600 hover:bg-slate-700">Back</button>
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_HOME')} className="remote-btn-md bg-blue-600 hover:bg-blue-700">Home</button>
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_MENU')} className="remote-btn-md bg-blue-600 hover:bg-blue-700">Menu</button>
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_SOURCE')} className="remote-btn-md bg-purple-600 hover:bg-purple-700">Source</button>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_CHUP')} className="remote-btn-md bg-purple-600 hover:bg-purple-700">CH+</button>
                                <button disabled={remoteBusy} onClick={() => sendGlobalKey('KEY_CHDOWN')} className="remote-btn-md bg-purple-600 hover:bg-purple-700">CH−</button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Individual TV Remote Modal */}
            {remoteOpen && remoteTV && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={closeRemoteModal}>
                    <div className="bg-gradient-to-b from-slate-800 to-slate-900 rounded-2xl shadow-2xl max-w-sm w-full mx-4 border border-slate-700" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-between p-5 border-b border-slate-700 bg-slate-800/50 rounded-t-2xl">
                            <h3 className="text-lg font-semibold text-slate-100">Remote: {remoteTV.name}</h3>
                            <button onClick={closeRemoteModal} className="text-slate-400 hover:text-slate-100 transition-colors">
                                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>
                        <div className="p-6">
                            <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_POWER')} className="remote-btn-lg bg-red-600 hover:bg-red-700 w-full mb-4">
                                <svg className="h-5 w-5 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728m-9.9-2.829a5 5 0 010-7.07m7.072 0a5 5 0 010 7.07M13 12a1 1 0 11-2 0 1 1 0 012 0z" />
                                </svg>
                                <span className="ml-2">Power</span>
                            </button>

                            <div className="grid grid-cols-3 gap-3 mb-4">
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_VOLDOWN')} className="remote-btn-md bg-blue-600 hover:bg-blue-700">Vol−</button>
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_MUTE')} className="remote-btn-md bg-orange-600 hover:bg-orange-700">
                                    <svg className="h-5 w-5 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" clipRule="evenodd" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
                                    </svg>
                                </button>
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_VOLUP')} className="remote-btn-md bg-blue-600 hover:bg-blue-700">Vol+</button>
                            </div>

                            <div className="bg-slate-800/50 rounded-xl p-4 mb-4">
                                <div className="grid grid-cols-3 gap-2">
                                    <div></div>
                                    <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_UP')} className="remote-btn-nav bg-slate-600 hover:bg-slate-700">
                                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 15l7-7 7 7" />
                                        </svg>
                                    </button>
                                    <div></div>
                                    <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_LEFT')} className="remote-btn-nav bg-slate-600 hover:bg-slate-700">
                                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M15 19l-7-7 7-7" />
                                        </svg>
                                    </button>
                                    <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_ENTER')} className="remote-btn-ok bg-green-600 hover:bg-green-700">OK</button>
                                    <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_RIGHT')} className="remote-btn-nav bg-slate-600 hover:bg-slate-700">
                                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                                        </svg>
                                    </button>
                                    <div></div>
                                    <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_DOWN')} className="remote-btn-nav bg-slate-600 hover:bg-slate-700">
                                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M19 9l-7 7-7-7" />
                                        </svg>
                                    </button>
                                    <div></div>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-3 mb-4">
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_RETURN')} className="remote-btn-md bg-slate-600 hover:bg-slate-700">Back</button>
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_HOME')} className="remote-btn-md bg-blue-600 hover:bg-blue-700">Home</button>
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_MENU')} className="remote-btn-md bg-blue-600 hover:bg-blue-700">Menu</button>
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_SOURCE')} className="remote-btn-md bg-purple-600 hover:bg-purple-700">Source</button>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_CHUP')} className="remote-btn-md bg-purple-600 hover:bg-purple-700">CH+</button>
                                <button disabled={remoteBusy} onClick={() => sendIndividualKey('KEY_CHDOWN')} className="remote-btn-md bg-purple-600 hover:bg-purple-700">CH−</button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default Home;