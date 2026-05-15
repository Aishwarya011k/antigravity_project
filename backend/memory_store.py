import logging

logger = logging.getLogger("MEMORY_STORE")

# In-memory storage structures
_latest_result = None
_history = []
_flagged_log = []
_source_status = {
    "gdacs": {"status": "connected", "count": 0},
    "reliefweb": {"status": "connected", "count": 0},
    "bluesky": {"status": "connected", "count": 0},
    "rss": {"status": "connected", "count": 0},
    "simulated": {"status": "loaded", "count": 0}
}

def save_result(result: dict) -> None:
    """Save the latest result and append to history (max 10)."""
    global _latest_result, _history
    try:
        _latest_result = result
        _history.insert(0, result)
        if len(_history) > 10:
            _history = _history[:10]
        logger.info(f"Saved new result. History length: {len(_history)}")
    except Exception as e:
        logger.error(f"Failed to save result: {e}")

def get_result() -> dict:
    """Get the latest result."""
    return _latest_result

def get_history() -> list:
    """Get the last 10 results."""
    return _history

def save_flagged(post: dict, reason: str) -> None:
    """Save a post to the misinformation log."""
    global _flagged_log
    try:
        log_entry = {
            "timestamp": post.get("timestamp", ""),
            "source": post.get("source", "unknown"),
            "reason": reason,
            "confidence": 0.5 # Default if not provided
        }
        _flagged_log.insert(0, log_entry)
        # Keep log size manageable
        if len(_flagged_log) > 100:
            _flagged_log = _flagged_log[:100]
    except Exception as e:
        logger.error(f"Failed to save flagged post: {e}")

def get_flagged_log() -> list:
    """Get the misinformation log."""
    return _flagged_log

def update_source_status(source: str, status: str, count: int) -> None:
    """Update the connection status and post count for a source."""
    global _source_status
    try:
        if source in _source_status:
            _source_status[source] = {"status": status, "count": count}
    except Exception as e:
        logger.error(f"Failed to update source status: {e}")

def get_source_status() -> dict:
    """Get the status of all sources."""
    return _source_status

def clear() -> None:
    """Clear all memory (useful for testing)."""
    global _latest_result, _history, _flagged_log
    _latest_result = None
    _history.clear()
    _flagged_log.clear()
