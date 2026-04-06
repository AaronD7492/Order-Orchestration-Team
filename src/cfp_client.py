import csv
import logging
from pathlib import Path

import paramiko

from src.config import Config

logger = logging.getLogger(__name__)

CITIES = ["Cambridge", "Kitchener", "Waterloo"]


def _sftp_connect():
    """Open an SFTP connection to the CFP server. Caller must close it."""
    transport = paramiko.Transport((Config.CFP_HOST, Config.CFP_PORT))
    transport.connect(username=Config.CFP_USER, password=Config.CFP_PASSWORD)
    sftp = paramiko.SFTPClient.from_transport(transport)
    return sftp, transport


def sync_primary_files():
    """
    Download all three CFP primary CSV files from the SFTP server to the
    local cache directory (CFP_CACHE_DIR).

    Called:
      - On app startup (non-blocking — failure is logged, not raised)
      - Ad-hoc when a client_id is not found in the local cache (per CFP spec)

    Files pulled:
      /primary/CFP-Cambridge.csv
      /primary/CFP-Kitchener.csv
      /primary/CFP-Waterloo.csv
    """
    cache_dir = Path(Config.CFP_CACHE_DIR)
    cache_dir.mkdir(exist_ok=True)

    sftp, transport = _sftp_connect()
    try:
        for city in CITIES:
            remote = f"/primary/CFP-{city}.csv"
            local = cache_dir / f"CFP-{city}.csv"
            sftp.get(remote, str(local))
            logger.info("CFP sync: pulled %s", remote)
    finally:
        sftp.close()
        transport.close()


def load_clients():
    """
    Parse all locally cached CFP CSVs into a dict keyed by clientID.

    Returns:
        {
            "A123": {
                "clientID":      "A123",
                "address":       "123 King St W",
                "mobile":        "5195550001",
                "deliveryCount": "4",
                "produce":       "2",
                "meat":          "1",
                "dairy":         "1",
                "city":          "Waterloo"   # derived from filename
            },
            ...
        }

    Returns an empty dict if no cached files exist yet.
    """
    clients = {}
    cache_dir = Path(Config.CFP_CACHE_DIR)

    for city in CITIES:
        local = cache_dir / f"CFP-{city}.csv"
        if not local.exists():
            continue
        with open(local, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                clients[row["clientID"]] = {**row, "city": city}

    return clients


def get_client(client_id):
    """
    Look up a single client by clientID.

    First checks the local cache. If not found, triggers an ad-hoc SFTP
    sync (per CFP spec) and retries once. Returns None if still not found
    or if the sync fails.

    Args:
        client_id: e.g. "A123"

    Returns:
        Client dict (see load_clients) or None
    """
    clients = load_clients()
    if client_id in clients:
        return clients[client_id]

    # Per CFP spec: trigger ad-hoc refresh when client not found locally
    logger.info("CFP: client '%s' not in local cache — triggering sync", client_id)
    try:
        sync_primary_files()
    except Exception as e:
        logger.error("CFP ad-hoc sync failed: %s", e)
        return None

    return load_clients().get(client_id)
