# TV WOL Service

Simple FastAPI service to send Wake-on-LAN (WOL) magic packets to TVs listed in `config/tvs.json`.

Quick start

- Install deps: `pip install -r requirements.txt`
- Run server: `python3 ./app/main.py` or `python -m uvicorn app.main:app --reload --port 8000`
- Endpoints:
  - GET `/tvs` — list TVs
  - GET `/tvs/{ip}` — get TV by IP
  - POST `/tvs/{ip}/wake` — send WOL packet (body: `{ "port": 9 }`), now sent as a unicast packet to the TV's IP
- GET `/tvs/status` — returns a JSON list with the online status (uses ping)
- GET `/status` — serves a small web UI (`status.html`) that shows TV statuses and allows sending WOL to individual TVs

Notes

- The service reads `config/tvs.json` on each request; you can update that file and calls will reflect the changes on next call.
- WOL is now sent as a unicast UDP packet to the TV's IP:port (default port 9).
- The status page uses ICMP ping (system `ping` command) to determine reachability; ensure your environment allows ping.
