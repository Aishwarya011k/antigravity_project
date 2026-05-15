import os
import json
import logging
from dataclasses import dataclass
from urllib.parse import urlparse
import openai
from serpapi import GoogleSearch

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("TRIAGE")

@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    snippet: str

@dataclass  
class TriageResult:
    verdict: str        # VERIFIED_REAL/FLAGGED
    confidence: float   # 0.0 to 1.0
    reasoning: str
    sources_found: int

TRUSTED_SOURCES = [
    "timesofindia.com", "ndtv.com", "thehindu.com", 
    "deccanherald.com", "newindianexpress.com", "indianexpress.com",
    "hindustantimes.com", "bbc.com", "reuters.com", "pti.in",
    "timesofindia.indiatimes.com"
]

def reverse_image_search(image_url: str) -> list[dict]:
    """Perform reverse image search using SerpApi."""
    try:
        api_key = os.getenv("SERPAPI_KEY")
        if not api_key:
            logger.error("Missing SERPAPI_KEY")
            return []

        params = {
            "engine": "google_reverse_image",
            "image_url": image_url,
            "api_key": api_key
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        return results.get("image_results", [])
    except Exception as e:
        logger.error(f"Reverse image search failed: {e}")
        return []

def filter_news_results(results: list[dict]) -> list[NewsItem]:
    """Filter search results to only include trusted news sources."""
    news_items = []
    try:
        for item in results:
            url = item.get("link", "")
            if not url:
                continue
            
            parsed_url = urlparse(url)
            netloc = parsed_url.netloc.lower()
            
            for source in TRUSTED_SOURCES:
                if netloc.endswith(source):
                    news_items.append(NewsItem(
                        title=item.get("title", ""),
                        url=url,
                        source=netloc,
                        snippet=item.get("snippet", "")
                    ))
                    break
    except Exception as e:
        logger.error(f"Error filtering news results: {e}")
    return news_items

def run_vlm_inference(image_url: str, news: list[NewsItem]) -> TriageResult:
    """Run VLM inference to verify image authenticity."""
    try:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            logger.error("Missing DEEPSEEK_API_KEY")
            return TriageResult("FLAGGED", 0.5, "Missing API key for triage", 0)

        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-vision")
        
        news_context = "\n".join([f"- {n.source}: {n.title} ({n.snippet})" for n in news])
        
        prompt = f"""
        Analyze this disaster image and the following news context to determine if it is real or fake/misinformation.
        News context:
        {news_context}
        
        Return ONLY a JSON object in this exact format:
        {{
            "verdict": "VERIFIED_REAL" or "FLAGGED",
            "confidence": float between 0.0 and 1.0,
            "reasoning": "string explaining the decision"
        }}
        """
        
        # Deepseek API currently requires chat completions
        # Deepseek Vision API might differ slightly, but we use standard OpenAI client for it
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a specialized disaster image verification AI. Output strictly JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        content = response.choices[0].message.content.strip()
        # Clean up markdown JSON formatting if present
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        data = json.loads(content)
        return TriageResult(
            verdict=data.get("verdict", "FLAGGED"),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=data.get("reasoning", "Failed to parse reasoning"),
            sources_found=len(news)
        )
    except Exception as e:
        logger.error(f"VLM inference failed: {e}")
        return TriageResult("FLAGGED", 0.5, f"VLM inference failed: {e}", len(news))

def _on_verified_real(result: TriageResult) -> str:
    return "ALLOW"

def _on_flagged(result: TriageResult) -> str:
    return "BLOCK"

def route(result: TriageResult) -> str:
    """Route based on triage result."""
    try:
        if result.verdict == "VERIFIED_REAL" and result.confidence >= 0.85:
            return _on_verified_real(result)
        return _on_flagged(result)
    except Exception as e:
        logger.error(f"Routing failed: {e}")
        return "BLOCK"

def run_pipeline(image_url: str) -> dict:
    """Run the complete image triage pipeline."""
    try:
        logger.info(f"Running triage for image: {image_url}")
        results = reverse_image_search(image_url)
        news = filter_news_results(results)
        triage_result = run_vlm_inference(image_url, news)
        action = route(triage_result)
        
        return {
            "verdict": triage_result.verdict,
            "confidence": triage_result.confidence,
            "reasoning": triage_result.reasoning,
            "sources_found": triage_result.sources_found,
            "action": action
        }
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return {
            "verdict": "FLAGGED",
            "confidence": 0.5,
            "reasoning": f"Pipeline failed: {e}",
            "sources_found": 0,
            "action": "BLOCK"
        }
