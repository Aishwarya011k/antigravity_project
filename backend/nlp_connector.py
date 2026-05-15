import logging
from nlp.scraper import scrape_all
from nlp.pipeline import run_nlp_pipeline
from nlp.triage_pipeline import run_pipeline as run_triage
from backend.memory_store import save_result

logger = logging.getLogger("NLP_CONNECTOR")

async def run_nlp_check(source: str, query: str = None) -> dict:
    """Run full NLP check."""
    try:
        posts = scrape_all()
        result = run_nlp_pipeline(posts, source=source)
        save_result(result)
        return result
    except Exception as e:
        logger.error(f"NLP check failed: {e}")
        return {"error": str(e), "source": source}

async def parse_voice_query(query: str) -> str:
    """Detect intent from voice query."""
    try:
        q = query.lower()
        if any(w in q for w in ["what to do", "how to", "should i"]):
            return "what_to_do"
        if any(w in q for w in ["which area", "where", "location", "affected"]):
            return "which_areas"
        if any(w in q for w in ["how many", "count", "reports"]):
            return "how_many"
        if any(w in q for w in ["how bad", "severity", "serious"]):
            return "how_bad"
        return "general"
    except Exception as e:
        logger.error(f"Voice query parsing failed: {e}")
        return "general"

async def build_voice_response(result: dict, intent: str) -> str:
    """Build a conversational response based on result and intent."""
    try:
        if intent == "what_to_do":
            return f"Here is what you should do: {result.get('advice')}"
            
        elif intent == "which_areas":
            locs = ", ".join(result.get('all_locations', []))
            return f"Affected areas include: {locs}"
            
        elif intent == "how_many":
            sources = ", ".join([k for k,v in result.get('sources', {}).items() if v > 0])
            return f"{result.get('posts_analyzed')} posts were detected across {sources}. {result.get('posts_flagged')} were flagged as misinformation."
            
        elif intent == "how_bad":
            return f"The current severity is {result.get('severity')} in {result.get('location')}. {result.get('posts_analyzed')} posts confirmed this disaster."
            
        else: # general
            return f"{result.get('disaster_type')} detected in {result.get('location')}. Severity is {result.get('severity')}. {result.get('advice')}"
            
    except Exception as e:
        logger.error(f"Failed to build voice response: {e}")
        return "Sorry, I could not process the response."

async def verify_image(image_url: str) -> dict:
    """Run image verification triage."""
    try:
        return run_triage(image_url)
    except Exception as e:
        logger.error(f"Image verification failed: {e}")
        return {"error": str(e)}
