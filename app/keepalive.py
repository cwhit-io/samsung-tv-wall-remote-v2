import asyncio
import random
import datetime
import logging

from app.config import load_tvs
import app.wol as wol
import app.utils as utils


logger = logging.getLogger("app.keepalive")


async def keepalive_loop(interval_seconds: int = 3600, start_hour: int = 6, end_hour: int = 18):
    """Background loop that pings each TV every `interval_seconds` while
    the current local time is between `start_hour` (inclusive) and
    `end_hour` (exclusive). If a TV is not responding to ping, a WOL packet
    is sent to its configured MAC address.

    Behavior:
    - Runs continuously until cancelled.
    - During active window (6..18 by default) checks all TVs once per interval.
    - Outside the window sleeps until the next start_hour.
    - Adds small per-device jitter to avoid bursts.
    """

    logger.info("Keepalive loop starting (interval=%ds window=%02d-%02d)", interval_seconds, start_hour, end_hour)

    try:
        while True:
            now = datetime.datetime.now()
            if start_hour <= now.hour < end_hour:
                tvs = load_tvs()
                if not tvs:
                    logger.debug("Keepalive: no TVs configured")
                for ip, data in tvs.items():
                    mac = data.get("mac")
                    if not mac:
                        logger.debug("Keepalive: skipping %s (no MAC)", ip)
                        continue

                    try:
                        # quick cached ping; cached results reduce network noise
                        online = utils.cached_ping_host(ip, timeout=1.0)
                        if not online:
                            logger.info("Keepalive: %s appears asleep — sending WOL", ip)
                            try:
                                wol.send_magic_packet_unicast(mac, ip, 9)
                            except Exception as e:
                                logger.exception("Keepalive: failed to send WOL to %s: %s", ip, e)
                        else:
                            logger.debug("Keepalive: %s is online", ip)
                    except Exception as e:
                        logger.exception("Keepalive: error checking %s: %s", ip, e)

                    # small jitter between devices
                    await asyncio.sleep(0.2 + random.random() * 0.8)

                # sleep until next run with slight jitter
                jitter = random.uniform(-0.05, 0.05) * interval_seconds
                sleep_for = max(60, interval_seconds + jitter)
                logger.info("Keepalive: completed iteration, sleeping %d seconds", int(sleep_for))
                await asyncio.sleep(sleep_for)

            else:
                # Calculate seconds until next start_hour
                next_start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                if now.hour >= end_hour:
                    next_start = next_start + datetime.timedelta(days=1)
                seconds = (next_start - now).total_seconds()
                logger.info("Keepalive: outside active window, sleeping %d seconds until %s", int(seconds), next_start.isoformat())
                await asyncio.sleep(max(60, seconds))

    except asyncio.CancelledError:
        logger.info("Keepalive loop cancelled, exiting")
        raise
    except Exception:
        logger.exception("Keepalive loop encountered an unexpected error and will exit")
        raise
