import os
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.nlp_connector import run_nlp_check
from backend.sms import send_sms_alert
from backend.memory_store import get_history

logger = logging.getLogger("SCHEDULER")
_scheduler = AsyncIOScheduler()
_check_count = 0
_ws_manager = None

async def scheduled_check():
    """The function that runs every interval."""
    global _check_count, _ws_manager
    _check_count += 1
    try:
        logger.info(f"Starting auto-check #{_check_count}")
        
        # Get previous severity before new check
        history = get_history()
        prev_severity = "LOW"
        if history:
            prev_severity = history[0].get("severity", "LOW")
            
        result = await run_nlp_check(source="auto")
        
        severity = result.get("severity", "LOW")
        location = result.get("location", "Unknown")
        posts = result.get("posts_analyzed", 0)
        
        logger.info(f"Check #{_check_count} complete. Severity: {severity}, Location: {location}, Posts: {posts}")
        
        # Severity comparison logic
        severity_levels = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        curr_level = severity_levels.get(severity, 1)
        prev_level = severity_levels.get(prev_severity, 1)
        
        if curr_level > prev_level:
            logger.info("Severity worsened. Sending SMS alert.")
            send_sms_alert(result)
        elif curr_level < prev_level:
            logger.info("Severity improved. No SMS sent.")
        else:
            logger.info("Severity unchanged. Skipping SMS to avoid spam.")
            
        # Broadcast to dashboard
        if _ws_manager:
            await _ws_manager.broadcast({"type": "auto_update", "result": result})
            
    except Exception as e:
        logger.error(f"Scheduled check failed: {e}")

def start_scheduler(app=None, manager=None):
    """Start the APScheduler."""
    global _scheduler, _ws_manager
    try:
        _ws_manager = manager
        interval = int(os.getenv("SCHEDULER_INTERVAL", "5"))
        _scheduler.add_job(scheduled_check, 'interval', minutes=interval)
        _scheduler.start()
        logger.info(f"Started scheduler — checking every {interval} minutes")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

def stop_scheduler():
    """Stop the APScheduler."""
    global _scheduler
    try:
        _scheduler.shutdown()
        logger.info("Stopped scheduler")
    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}")

async def force_check() -> dict:
    """Manually force a check."""
    logger.info("Forcing manual check...")
    result = await run_nlp_check(source="manual")
    if _ws_manager:
        await _ws_manager.broadcast({"type": "manual_update", "result": result})
    return result
