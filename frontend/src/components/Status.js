import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

const Status = () => {
    const [tvs, setTvs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const navigate = useNavigate();

    const fetchStatus = useCallback(async (force = false) => {
        setError(null);
        try {
            const url = force ? '/api/tvs/status?force=true' : '/api/tvs/status';
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setTvs(data);
        } catch (e) {
            setError(e.message || 'Error fetching status');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus(false);
        const id = setInterval(() => fetchStatus(false), 10000);
        return () => clearInterval(id);
    }, [fetchStatus]);

    const refreshNow = async () => {
        setLoading(true);
        await fetchStatus(true);
    };

    return (
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-slate-100">TV Status Dashboard</h2>
                    <p className="mt-1 text-sm text-slate-400">Auto-refresh every 10 seconds. Click a row to open the debug page for that TV.</p>
                </div>
                <button onClick={refreshNow} id="btnRefresh"
                    className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    disabled={loading}
                >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    {loading ? 'Refreshing...' : 'Refresh'}
                </button>
            </div>

            <div className="bg-slate-900 rounded-lg shadow-xl border border-slate-800 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-700" id="tv-table">
                        <thead className="bg-slate-800">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">IP Address</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Name</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">MAC Address</th>
                                <th className="px-6 py-3 text-center text-xs font-medium text-slate-400 uppercase tracking-wider">Ping</th>
                                <th className="px-6 py-3 text-center text-xs font-medium text-slate-400 uppercase tracking-wider">WebSocket</th>
                                <th className="px-6 py-3 text-center text-xs font-medium text-slate-400 uppercase tracking-wider">Power State</th>
                            </tr>
                        </thead>
                        <tbody className="bg-slate-900 divide-y divide-slate-800">
                            {error && (
                                <tr>
                                    <td colSpan={6} className="px-6 py-4 text-center text-red-400">{error}</td>
                                </tr>
                            )}

                            {!error && tvs.length === 0 && !loading && (
                                <tr>
                                    <td colSpan={6} className="px-6 py-4 text-center text-slate-400">No TVs found</td>
                                </tr>
                            )}

                            {tvs.map(tv => {
                                const statusOnline = tv.online ? (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-800">Online</span>
                                ) : (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400 border border-red-800">Offline</span>
                                );

                                const ws = tv.ws_online ? (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-800">Open</span>
                                ) : (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">Closed</span>
                                );

                                let powerState = <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">Unknown</span>;
                                if (tv.power_state) {
                                    const state = String(tv.power_state).toLowerCase();
                                    if (state === 'on') powerState = <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-800">On</span>;
                                    else if (state === 'standby') powerState = <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-900/30 text-orange-400 border border-orange-800">Standby</span>;
                                    else if (state === 'off') powerState = <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400 border border-red-800">Off</span>;
                                    else powerState = <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">{tv.power_state}</span>;
                                }

                                return (
                                    <tr key={tv.ip} className="hover:bg-slate-800/50 transition-colors cursor-pointer" onClick={() => navigate(`/debug?ip=${encodeURIComponent(tv.ip)}`)}>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-slate-200">{tv.ip}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-slate-100">{tv.name}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-slate-400">{tv.mac}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-center text-sm">{statusOnline}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-center text-sm">{ws}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-center text-sm">{powerState}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>

            {loading && (
                <div id="loading" className="text-center py-8">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
                    <p className="mt-2 text-sm text-slate-400">Loading TV status...</p>
                </div>
            )}
        </main>
    );
};

export default Status;