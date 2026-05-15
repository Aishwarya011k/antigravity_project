import logging
from datetime import datetime
import spacy
from transformers import pipeline as hf_pipeline
from .scraper import scrape_all
from .triage_pipeline import run_pipeline as run_triage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("NLP")

# Initialize models
try:
    nlp_spacy = spacy.load("en_core_web_sm")
    # Load zero-shot classifier lazily or mock if not available immediately to save startup time
    classifier = hf_pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
except Exception as e:
    logger.error(f"Failed to load models: {e}")
    nlp_spacy = None
    classifier = None

LABELS = ["Flood", "Cyclone", "Fire", "Earthquake", "Landslide", "None"]

KNOWN_LOCATIONS = [
    "Mangalore", "Udupi", "Dakshina Kannada",
    "Uttara Kannada", "Coastal Karnataka",
    "Karnataka", "Kerala"
]

def fallback_classifier(text: str) -> str:
    """Keyword based fallback classification."""
    text_lower = text.lower()
    keywords = {
        "Flood": ["flood", "flooding", "inundation", "waterlogging", "overflow", "deluge"],
        "Cyclone": ["cyclone", "hurricane", "storm", "typhoon", "wind", "gale"],
        "Fire": ["fire", "wildfire", "blaze", "burn"],
        "Earthquake": ["earthquake", "tremor", "quake", "seismic"],
        "Landslide": ["landslide", "mudslide", "rockfall", "collapse"]
    }
    
    for label, words in keywords.items():
        if any(w in text_lower for w in words):
            return label
    return "None"

def classify_post(post: dict) -> str:
    """Step 2A: Classify disaster type."""
    if post.get("disaster_hint"):
        return post["disaster_hint"]
        
    text = post.get("text", "")
    try:
        if classifier:
            res = classifier(text, LABELS)
            best_label = res["labels"][0]
            confidence = res["scores"][0]
            if confidence < 0.4:
                return "None"
            return best_label
    except Exception as e:
        logger.warning(f"HF classifier failed: {e}. Using fallback.")
        
    return fallback_classifier(text)

def extract_location(text: str) -> str:
    """Step 2B: Extract Location."""
    try:
        if nlp_spacy:
            doc = nlp_spacy(text)
            entities = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]
            
            for ent in entities:
                for known in KNOWN_LOCATIONS:
                    if known.lower() in ent.lower():
                        return known
    except Exception as e:
        logger.warning(f"spaCy extraction failed: {e}")
        
    # Simple keyword match
    for known in KNOWN_LOCATIONS:
        if known.lower() in text.lower():
            return known
            
    return "Karnataka" # Default

def score_severity(text: str) -> int:
    """Step 2C: Severity Scoring."""
    text_lower = text.lower()
    high_keywords = ["sos", "stranded", "evacuate", "emergency", "deaths", "collapse", "rescue needed", "critical", "trapped", "missing"]
    medium_keywords = ["waterlogging", "road blocked", "flooding", "strong winds", "closed", "damaged", "displaced", "warning", "alert"]
    low_keywords = ["light rain", "advisory", "cloudy", "weather warning", "monitoring"]
    
    if any(k in text_lower for k in high_keywords):
        return 3
    if any(k in text_lower for k in medium_keywords):
        return 2
    if any(k in text_lower for k in low_keywords):
        return 1
    return 1 # Default LOW

def run_nlp_pipeline(posts: list[dict], source: str = "auto") -> dict:
    """Process all posts and return final aggregated result."""
    logger.info(f"Processing {len(posts)} posts from source: {source}")
    
    highest_severity_score = 0
    type_counts = {}
    all_locations = set()
    posts_flagged = 0
    source_counts = {"gdacs": 0, "reliefweb": 0, "bluesky": 0, "rss": 0, "simulated": 0}
    
    best_location = "Karnataka"
    
    for post in posts:
        # Step 2D: Image Triage
        if post.get("image_url"):
            triage_res = run_triage(post["image_url"])
            if triage_res.get("action") == "BLOCK":
                posts_flagged += 1
                logger.info(f"Flagged post {post['id']} due to misinformation.")
                continue # Skip this post
            elif triage_res.get("verdict") == "VERIFIED_REAL":
                post["severity_boost"] = 1 # Will add to severity later
        
        # Step 2A: Classify
        d_type = classify_post(post)
        if d_type != "None":
            type_counts[d_type] = type_counts.get(d_type, 0) + 1
            
        # Step 2B: Location
        loc = extract_location(post.get("text", ""))
        if loc:
            all_locations.add(loc)
            
        # Step 2C: Severity
        sev = score_severity(post.get("text", ""))
        sev += post.get("severity_boost", 0)
        
        if sev > highest_severity_score:
            highest_severity_score = sev
            best_location = loc
            
        # Count sources
        src = post.get("source")
        if src in source_counts:
            source_counts[src] += 1
            
    # Aggregation
    most_common_type = "None"
    if type_counts:
        most_common_type = max(type_counts, key=type_counts.get)
        
    severity_str = "LOW"
    if highest_severity_score >= 3:
        severity_str = "HIGH"
    elif highest_severity_score == 2:
        severity_str = "MEDIUM"
        
    # Build Advice
    if severity_str == "HIGH":
        advice = "Evacuate immediately. Move to higher ground. Avoid flooded roads. Call NDRF: 011-24363260. Check dashboard for relief centers."
    elif severity_str == "MEDIUM":
        advice = "Stay indoors. Avoid coastal areas. Keep emergency kit ready. Monitor VoiceGuard dashboard."
    else:
        advice = "No immediate threat. Stay informed. Normal activities can continue."
        
    result = {
        "disaster_type": most_common_type if most_common_type != "None" else "No disaster",
        "location": best_location if best_location else "Karnataka",
        "severity": severity_str,
        "advice": advice,
        "posts_analyzed": len(posts) - posts_flagged,
        "posts_flagged": posts_flagged,
        "all_locations": list(all_locations) if all_locations else ["Karnataka"],
        "sources": source_counts,
        "timestamp": datetime.now().isoformat(),
        "source": source
    }
    
    logger.info(f"Pipeline complete. Severity: {severity_str}, Location: {best_location}")
    return result
