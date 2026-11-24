import asyncio
import random
import logging

from app.config import load_tvs
import app.wol as wol
import app.utils as utils


logger = logging.getLogger("app.keepalive")


async def keepalive_loop(interval_seconds: int = 3600):
    """Background loop that pings each TV every interval_seconds, all day.

    If a TV does not respond to ping, a WOL packet is sent to its configured
    MAC address.

    Behavior:
    - Runs continuously until cancelled.
    - Checks all TVs once per interval, 24 hours a day.
    - Adds small per-device jitter to avoid bursts.
    """

    logger.info("Keepalive loop starting (interval=%ds, all day)", interval_seconds)

    try:
        while True:
            tvs = load_tvs()
            if not tvs:
                logger.debug("Keepalive: no TVs configured")
            for ip, data in tvs.items():
                mac = data.get("mac")
                if not mac:
                    logger.debug("Keepalive: skipping %s (no MAC)", ip)
                    continue

                try:
                    online = utils.cached_ping_host(ip, timeout=1.0)
                    if not online:
                        logger.info("Keepalive: %s appears asleep ? sending WOL", ip)
                        try:
                            wol.send_magic_packet_unicast(mac, ip, 9)
                        except Exception as e:
                            logger.exception("Keepalive: failed to send WOL to %s: %s", ip, e)
                    else:
                        logger.debug("Keepalive: %s is online", ip)
                except Exception as e:
                    logger.exception("Keepalive: error checking %s: %s", ip, e)

                await asyncio.sleep(0.2 + random.random() * 0.8)

            jitter = random.uniform(-0.05, 0.05) * interval_seconds
            sleep_for = max(60, interval_seconds + jitter)
            logger.info("Keepalive: completed iteration, sleeping %d seconds", int(sleep_for))
            await asyncio.sleep(sleep_for)

    except asyncio.CancelledError:
        logger.info("Keepalive loop cancelled, exiting")
        raise
    except Exception:
        logger.exception("Keepalive loop encountered an unexpected error and will exit")
        raise
