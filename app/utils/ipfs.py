import os
import json
import requests
import logging
from dotenv import load_dotenv

# Load env variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

logger = logging.getLogger(__name__)

PINATA_API_KEY = os.environ.get("PINATA_API_KEY")
PINATA_API_SECRET = os.environ.get("PINATA_API_SECRET")

def upload_to_ipfs(json_data: dict) -> str:
    """
    Uploads a JSON dictionary to IPFS using Pinata API.
    Returns the CID (Content Identifier) string if successful, else None.
    """
    if not PINATA_API_KEY or not PINATA_API_SECRET:
        logger.error("[IPFS] PINATA_API_KEY or PINATA_API_SECRET missing in .env")
        return None

    url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    headers = {
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_API_SECRET,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json={"pinataContent": json_data}, timeout=15)
        response.raise_for_status()
        cid = response.json().get("IpfsHash")
        logger.info(f"[IPFS] Successfully uploaded payload. CID: {cid}")
        return cid
    except Exception as e:
        logger.error(f"[IPFS] Upload failed: {e}")
        return None

def fetch_from_ipfs(cid: str) -> dict:
    """
    Fetches JSON payload from IPFS using a public gateway.
    Returns the JSON dictionary if successful, else None.
    """
    gateways = [
        f"https://gateway.pinata.cloud/ipfs/{cid}",
        f"https://ipfs.io/ipfs/{cid}",
        f"https://cloudflare-ipfs.com/ipfs/{cid}"
    ]

    for gw in gateways:
        try:
            response = requests.get(gw, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning(f"[IPFS] Failed to fetch from gateway {gw}: {e}")
            continue

    logger.error(f"[IPFS] Could not fetch CID {cid} from any gateways.")
    return None
