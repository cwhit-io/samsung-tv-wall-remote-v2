import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';

const RESOLUME_URL = 'http://10.10.97.83:8080/';

function navLinkClass({ isActive }, activeClass) {
    const base = 'px-3 py-2 rounded-md text-sm font-medium transition-colors';
    if (isActive) return `${base} ${activeClass}`;
    return `${base} text-slate-300 hover:text-slate-100 hover:bg-slate-800`;
}

const Layout = () => {
    const year = new Date().getFullYear();

    return (
        <div className="min-h-screen bg-slate-950 flex flex-col">
            <header className="bg-slate-900 border-b border-slate-800 shadow-lg">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        <div className="flex items-center">
                            <svg className="h-8 w-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                                    d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                            <h1 className="ml-3 text-xl font-semibold text-slate-100">TV Control Panel</h1>
                        </div>
                        <nav className="flex space-x-4">
                            <NavLink to="/" className={(s) => navLinkClass(s, 'text-blue-400 bg-blue-950/50')}>Home</NavLink>
                            <NavLink to="/status" className={(s) => navLinkClass(s, 'text-blue-400 bg-blue-950/50')}>Status</NavLink>
                            <NavLink to="/debug" className={(s) => navLinkClass(s, 'text-green-400 bg-green-950/50')}>Debug</NavLink>
                            <a href={RESOLUME_URL} target="_blank" rel="noreferrer"
                                className="px-3 py-2 rounded-md text-sm font-medium text-slate-300 hover:text-slate-100 hover:bg-slate-800 transition-colors">
                                Resolume
                            </a>
                        </nav>
                    </div>
                </div>
            </header>

            <Outlet />

            <footer className="mt-auto bg-slate-900 border-t border-slate-800">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <div className="flex items-center justify-between">
                        <p className="text-sm text-slate-500">
                            © {year} TV Control Panel. Built with FastAPI & React.
                        </p>
                        <div className="flex space-x-4 text-sm text-slate-500">
                            <a href="https://github.com/cwhit-io/tv2" target="_blank" rel="noreferrer" className="hover:text-slate-300 transition-colors">GitHub</a>
                            <a href="/api/tvs" className="hover:text-slate-300 transition-colors">API</a>
                            <a href="/api/docs" className="hover:text-slate-300 transition-colors">Docs</a>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
};

export default Layout;
