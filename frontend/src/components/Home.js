import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

const Home = () => {
    const [tvData, setTvData] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchTVs();
    }, []);

    const fetchTVs = async () => {
        try {
            const res = await fetch('/api/tvs/status');
            if (!res.ok) throw new Error('Failed to fetch TVs');
            const data = await res.json();
            setTvData(data);
            setLoading(false);
        } catch (error) {
            console.error('Error fetching TVs:', error);
            setLoading(false);
        }
    };

    const togglePower = async (ip, name) => {
        try {
            const res = await fetch(`/api/tvs/${encodeURIComponent(ip)}/power`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (res.ok) {
                fetchTVs(); // Refresh data
            } else {
                alert(`Failed to toggle power for ${name}`);
            }
        } catch (error) {
            alert(`Error toggling power for ${name}`);
        }
    };

    const openRemoteModal = (ip, name) => {
        // Implement remote modal
        alert(`Open remote for ${name}`);
    };

    const sortedTVs = [...tvData].sort((a, b) => {
        const getOrder = (name) => {
            const match = name.match(/([TMB])(\d+)/i);
            if (!match) return 999;
            const letter = match[1].toUpperCase();
            const num = parseInt(match[2]);
            if (letter === 'T') return num;
            if (letter === 'M') return 100 + num;
            if (letter === 'B') return 200 + num;
            return 999;
        };
        return getOrder(a.name) - getOrder(b.name);
    });

    return (
        <>
            <header className="bg-slate-900 border-b border-slate-800 shadow-lg">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        <div className="flex items-center">
                            <svg className="h-8 w-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                                    d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                            <h1 className="ml-3 text-xl font-semibold text-slate-100">TV Control Panel (React)</h1>
                        </div>
                        <nav className="flex space-x-4">
                            <Link to="/" className="px-3 py-2 rounded-md text-sm font-medium text-blue-400 bg-blue-950/50">Home</Link>
                            <Link to="/status" className="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-slate-100 hover:bg-slate-800 transition-colors">Status</Link>
                            <Link to="/debug" className="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-slate-100 hover:bg-slate-800 transition-colors">Debug</Link>
                        </nav>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="mb-6 flex items-center justify-between">
                    <h2 className="text-2xl font-bold text-slate-100">TV Grid</h2>
                    <button onClick={fetchTVs} className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors flex items-center gap-2">
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        Refresh
                    </button>
                </div>

                {loading ? (
                    <div className="text-center py-16">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                        <p className="mt-4 text-sm text-slate-400">Loading TVs...</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-5 gap-4">
                        {sortedTVs.map(tv => {
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

                            return (
                                <div key={tv.ip} className={`tv-card ${tv.online ? 'online' : 'offline'}`}>
                                    <div className="tv-card-content">
                                        <div className="flex items-start justify-between">
                                            <div className="text-lg font-bold text-slate-100">{tv.name}</div>
                                            <div className={`text-2xl ${powerColor}`} title={powerState}>{powerIcon}</div>
                                        </div>

                                        <div className="tv-screen">
                                            <svg className={`w-full h-full ${tv.online ? 'text-slate-600' : 'text-slate-800'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5"
                                                    d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                            </svg>
                                        </div>

                                        <div className="flex items-center gap-2">
                                            <button onClick={() => togglePower(tv.ip, tv.name)}
                                                className="flex-1 px-3 py-2 text-xs font-medium rounded-md text-slate-400 bg-transparent hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-500 transition-colors flex items-center justify-center">
                                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M18.36 6.64a9 9 0 1 1-12.73 0" />
                                                    <line x1="12" x2="12" y1="2" y2="12" />
                                                    <line x1="12" x2="12.01" y1="22" y2="18" />
                                                </svg>
                                            </button>
                                            <button onClick={() => openRemoteModal(tv.ip, tv.name)}
                                                className="flex-1 px-3 py-2 text-xs font-medium rounded-md text-slate-400 bg-transparent hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-500 transition-colors flex items-center justify-center">
                                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <line x1="6" x2="10" y1="11" y2="11" strokeWidth="3" />
                                                    <line x1="8" x2="8" y1="9" y2="13" strokeWidth="3" />
                                                    <line x1="15" x2="15.01" y1="12" y2="12" strokeWidth="3" />
                                                    <line x1="18" x2="18.01" y1="10" y2="14" strokeWidth="3" />
                                                    <path strokeWidth="3" d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16H14.17a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258A4 4 0 0 0 17.32 5z" />
                                                </svg>
                                            </button>
                                            <Link to={`/debug?ip=${encodeURIComponent(tv.ip)}`}
                                                className="flex-1 px-3 py-2 text-xs font-medium rounded-md text-slate-400 bg-transparent hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-500 transition-colors flex items-center justify-center">
                                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <polyline strokeWidth="3" points="4,17 10,11 4,5" />
                                                    <line strokeWidth="3" x1="12" x2="20" y1="19" y2="19" />
                                                </svg>
                                            </Link>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </main>
        </>
    );
};

export default Home;