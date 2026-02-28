import os
import requests

API_BASE = "https://api.supermemory.ai"
API_KEY = os.environ.get("SUPERMEMORY_API_KEY", "")


def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }


def add_memory(content, container_tags, custom_id=None, metadata=None):
    """Store a memory (finding, inspection record, etc.) in Supermemory.
    container_tags is a list like ['CAT0325F4K01847', 'fleet_CAT_325']."""
    payload = {
        "content": content,
        "containerTags": container_tags,
    }
    if custom_id:
        payload["customId"] = custom_id
    if metadata:
        payload["metadata"] = metadata

    resp = requests.post(
        f"{API_BASE}/v3/documents",
        json=payload,
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()


def search_memories(query, container_tag=None, limit=10):
    """Semantic search across memories. Optionally filter by containerTag."""
    payload = {
        "q": query,
        "limit": limit,
        "searchMode": "hybrid",
    }
    if container_tag:
        payload["containerTag"] = container_tag

    resp = requests.post(
        f"{API_BASE}/v4/search",
        json=payload,
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()


def query_unit_history(serial, zone, limit=5):
    """Query past inspection findings for a specific zone on a specific unit."""
    return search_memories(
        query=f"{zone} inspection findings and condition history",
        container_tag=serial,
        limit=limit,
    )


def query_fleet_stats(fleet_tag, zone, limit=5):
    """Query fleet-wide patterns for a component zone."""
    return search_memories(
        query=f"{zone} failure rates, common issues, fleet patterns",
        container_tag=fleet_tag,
        limit=limit,
    )


def store_inspection_findings(findings, unit_serial, fleet_tag, inspection_id):
    """After inspection, store each finding in both unit and fleet containers."""
    results = []
    for finding in findings:
        content = (
            f"Inspection {inspection_id}: "
            f"Zone={finding['zone']}, "
            f"Rating={finding['rating']}, "
            f"Description={finding.get('description', '')}, "
            f"Spec={finding.get('spec_reference', 'N/A')}"
        )
        tags = [unit_serial, fleet_tag]
        custom_id = f"{inspection_id}_{finding['zone']}"
        metadata = {
            "zone": finding["zone"],
            "rating": finding["rating"],
            "inspection_id": inspection_id,
        }
        r = add_memory(content, tags, custom_id=custom_id, metadata=metadata)
        results.append(r)
    return results
