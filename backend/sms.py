import os
import logging
from twilio.rest import Client # pyrefly: ignore [missing-import]
from backend.memory_store import get_history

logger = logging.getLogger("SMS")

def send_sms_alert(result: dict) -> None:
    """Send SMS alert for MEDIUM or HIGH severity disasters if it worsened."""
    try:
        current_severity = result.get("severity", "LOW")
        if current_severity not in ["MEDIUM", "HIGH"]:
            logger.info("Severity is LOW, no SMS sent.")
            return

        history = get_history()
        
        # DEMO MODE: Always send the first 3 alerts of the session
        if len(history) <= 3:
            logger.info(f"Demo Mode: Sending alert {len(history)} of 3 regardless of severity change.")
        else:
            previous_severity = "LOW"
            if len(history) > 1:
                previous_severity = history[1].get("severity", "LOW")
                
            severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
            prev_rank = severity_rank.get(previous_severity, 1)
            curr_rank = severity_rank.get(current_severity, 1)

            if curr_rank <= prev_rank:
                logger.info(f"Severity did not worsen (prev: {previous_severity}, curr: {current_severity}). SMS skipped.")
                return

        sid = os.getenv("TWILIO_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        from_num = os.getenv("TWILIO_FROM")
        alert_numbers = os.getenv("ALERT_NUMBERS", "")

        if not sid or not token or not from_num or not alert_numbers:
            logger.warning("Twilio credentials or alert numbers missing. SMS skipped.")
            return

        client = Client(sid, token)
        numbers = [n.strip() for n in alert_numbers.split(",") if n.strip()]

        message_body = (
            f"VOICEGUARD ALERT — {result.get('location')}\n"
            f"Risk: {current_severity}\n"
            f"Disaster: {result.get('disaster_type')}\n"
            f"Action: {result.get('advice')}\n"
            f"Posts detected: {result.get('posts_analyzed')}\n"
            f"Time: {result.get('timestamp')}\n"
            f"VoiceGuard AI — AVINYA 2026"
        )

        for number in numbers:
            try:
                message = client.messages.create(
                    body=message_body,
                    from_=from_num,
                    to=number
                )
                logger.info(f"SMS sent to {number}. SID: {message.sid}")
            except Exception as e:
                logger.error(f"Failed to send SMS to {number}: {e}")

    except Exception as e:
        logger.error(f"SMS alert generation failed: {e}")

def test_sms() -> bool:
    """Send a test SMS message."""
    try:
        sid = os.getenv("TWILIO_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        from_num = os.getenv("TWILIO_FROM")
        alert_numbers = os.getenv("ALERT_NUMBERS", "")

        if not sid or not token or not from_num or not alert_numbers:
            logger.warning("Twilio credentials missing for test SMS.")
            return False

        client = Client(sid, token)
        number = [n.strip() for n in alert_numbers.split(",") if n.strip()][0]

        message = client.messages.create(
            body="VOICEGUARD AI: This is a test SMS message.",
            from_=from_num,
            to=number
        )
        logger.info(f"Test SMS sent to {number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Test SMS failed: {e}")
        return False
