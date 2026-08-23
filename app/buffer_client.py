"""Buffer publishing client. DRY_RUN=true by default: nothing is sent."""
from __future__ import annotations
import requests

from . import config

API = "https://api.bufferapp.com/1"


def publish_post(text: str, profile_ids: list[str] | None = None) -> dict:
    profiles = profile_ids or config.BUFFER_PROFILE_IDS
    if config.DRY_RUN or not config.BUFFER_ACCESS_TOKEN or not profiles:
        return {"dry_run": True, "text": text[:80], "profiles": profiles}
    results = []
    for pid in profiles:
        r = requests.post(f"{API}/updates/create.json", data={
            "access_token": config.BUFFER_ACCESS_TOKEN,
            "profile_ids[]": pid, "text": text, "now": "false",
        }, timeout=30)
        r.raise_for_status()
        results.append(r.json())
    return {"dry_run": False, "results": results}
