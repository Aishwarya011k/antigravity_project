import os
import json
import uuid
import logging
import requests
import feedparser
from datetime import datetime, timedelta
from atproto import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("SCRAPER")

def scrape_gdacs() -> list[dict]:
    """Scrape UN GDACS feed."""
    posts = []
    try:
        feed = feedparser.parse("https://www.gdacs.org/xml/rss.xml")
        event_map = {
            "FL": "Flood", "TC": "Cyclone", "EQ": "Earthquake",
            "WF": "Fire", "DR": "Landslide"
        }
        severity_map = {"Red": 90, "Orange": 60, "Green": 30}
        
        for entry in feed.entries:
            try:
                # GDACS specific fields
                country = entry.get("gdacs_country", "")
                if country not in ["India", "IND"] and "India" not in entry.title and "Karnataka" not in entry.title and "Kerala" not in entry.title:
                    continue
                    
                event_type = entry.get("gdacs_eventtype", "")
                mapped_type = event_map.get(event_type, None)
                
                alert_level = entry.get("gdacs_alertlevel", "Green")
                score = severity_map.get(alert_level, 30)
                
                posts.append({
                    "id": f"gdacs_{uuid.uuid4().hex[:8]}",
                    "text": entry.get("summary", entry.title),
                    "title": entry.title,
                    "url": entry.link,
                    "image_url": None,
                    "source": "gdacs",
                    "timestamp": entry.get("published", datetime.now().isoformat()),
                    "score": score,
                    "disaster_hint": mapped_type
                })
            except Exception as e:
                logger.warning(f"Error parsing GDACS entry: {e}")
    except Exception as e:
        logger.error(f"GDACS scraping failed: {e}")
    return posts

def scrape_reliefweb() -> list[dict]:
    """Scrape UN ReliefWeb API."""
    posts = []
    try:
        headers = {"User-Agent": "voiceguardai"}
        # Endpoint 1: Disasters
        url1 = "https://api.reliefweb.int/v1/disasters"
        params1 = {
            "appname": "voiceguardai",
            "filter[conditions][0][field]": "country.iso3",
            "filter[conditions][0][value]": "IND",
            "filter[conditions][1][field]": "status",
            "filter[conditions][1][value]": "ongoing",
            "fields[include][]": ["name", "glide", "date", "type", "status"],
            "sort[]": "date:desc",
            "limit": 10
        }
        res1 = requests.get(url1, params=params1, headers=headers)
        if res1.status_code == 200:
            for item in res1.json().get("data", []):
                fields = item.get("fields", {})
                name = fields.get("name", "")
                
                # Map type
                hint = None
                name_lower = name.lower()
                for t in ["flood", "cyclone", "earthquake", "landslide", "fire"]:
                    if t in name_lower:
                        hint = t.capitalize()
                        break
                        
                posts.append({
                    "id": f"rw_dis_{item.get('id', uuid.uuid4().hex[:8])}",
                    "text": name,
                    "title": name,
                    "url": item.get("href", ""),
                    "image_url": None,
                    "source": "reliefweb",
                    "timestamp": fields.get("date", {}).get("created", datetime.now().isoformat()),
                    "score": 60,
                    "disaster_hint": hint
                })
                
        # Endpoint 2: Reports
        url2 = "https://api.reliefweb.int/v1/reports"
        params2 = {
            "appname": "voiceguardai",
            "filter[conditions][0][field]": "country.iso3",
            "filter[conditions][0][value]": "IND",
            "fields[include][]": ["title", "body-html", "date", "source", "url"],
            "sort[]": "date:desc",
            "limit": 10
        }
        res2 = requests.get(url2, params=params2, headers=headers)
        if res2.status_code == 200:
            for item in res2.json().get("data", []):
                fields = item.get("fields", {})
                title = fields.get("title", "")
                body = fields.get("body-html", "")
                
                import re
                clean_body = re.sub('<[^<]+>', '', body)[:500]
                
                hint = None
                title_lower = title.lower()
                for t in ["flood", "cyclone", "earthquake", "landslide", "fire"]:
                    if t in title_lower:
                        hint = t.capitalize()
                        break
                        
                posts.append({
                    "id": f"rw_rep_{item.get('id', uuid.uuid4().hex[:8])}",
                    "text": clean_body,
                    "title": title,
                    "url": fields.get("url", ""),
                    "image_url": None,
                    "source": "reliefweb",
                    "timestamp": fields.get("date", {}).get("created", datetime.now().isoformat()),
                    "score": 50,
                    "disaster_hint": hint
                })
    except Exception as e:
        logger.error(f"ReliefWeb scraping failed: {e}")
    return posts

def scrape_bluesky() -> list[dict]:
    """Scrape Bluesky API."""
    posts = []
    try:
        handle = os.getenv("BLUESKY_HANDLE")
        password = os.getenv("BLUESKY_PASSWORD")
        
        # Simplified public search fallback if no auth
        if not handle or not password:
            logger.info("Using Bluesky public fallback search")
            url = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
            for q in ["flood Karnataka", "cyclone India", "disaster Mangalore", "earthquake India"]:
                try:
                    res = requests.get(url, params={"q": q, "limit": 10})
                    if res.status_code == 200:
                        for p in res.json().get("posts", []):
                            record = p.get("record", {})
                            posts.append({
                                "id": f"bsky_{p.get('uri', uuid.uuid4().hex).split('/')[-1]}",
                                "text": record.get("text", ""),
                                "title": record.get("text", "")[:50],
                                "url": f"https://bsky.app/profile/{p.get('author', {}).get('handle')}/post/{p.get('uri', '').split('/')[-1]}",
                                "image_url": None, # Complex to extract from public without auth
                                "source": "bluesky",
                                "timestamp": record.get("createdAt", datetime.now().isoformat()),
                                "score": p.get("likeCount", 0) + p.get("repostCount", 0),
                                "disaster_hint": None
                            })
                except Exception as e:
                    logger.warning(f"Bluesky public search failed for '{q}': {e}")
            return posts

        client = Client()
        client.login(handle, password)
        
        keywords = [
            "flood Karnataka", "cyclone India", "disaster Mangalore",
            "flood Udupi", "earthquake India", "emergency Karnataka"
        ]
        
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        
        for q in keywords:
            try:
                response = client.app.bsky.feed.search_posts({"q": q, "limit": 10})
                for p in response.posts:
                    record = getattr(p, "record", None)
                    if not record:
                        continue
                    
                    created_at = getattr(record, "created_at", "")
                    if created_at < yesterday:
                        continue
                        
                    image_url = None
                    embed = getattr(record, "embed", None)
                    if embed and hasattr(embed, "images") and embed.images:
                        image_url = embed.images[0].image.ref
                    
                    posts.append({
                        "id": f"bsky_{p.uri.split('/')[-1]}",
                        "text": getattr(record, "text", ""),
                        "title": getattr(record, "text", "")[:50],
                        "url": f"https://bsky.app/profile/{p.author.handle}/post/{p.uri.split('/')[-1]}",
                        "image_url": image_url,
                        "source": "bluesky",
                        "timestamp": created_at,
                        "score": getattr(p, "like_count", 0) + getattr(p, "repost_count", 0),
                        "disaster_hint": None
                    })
            except Exception as e:
                logger.warning(f"Bluesky authenticated search failed for '{q}': {e}")

    except Exception as e:
        logger.error(f"Bluesky scraping failed: {e}")
    return posts

def scrape_rss() -> list[dict]:
    """Scrape RSS news feeds."""
    posts = []
    feeds = [
        "https://feeds.feedburner.com/ndtvnews-india-news",
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://www.deccanherald.com/rss-feeds/national.rss"
    ]
    keywords = ["flood", "cyclone", "disaster", "earthquake", "landslide", 
                "storm", "rescue", "evacuate", "emergency", "mangalore", 
                "udupi", "karnataka"]
    
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.title
                summary = entry.get("summary", "")
                combined = (title + " " + summary).lower()
                
                if any(k in combined for k in keywords):
                    hint = None
                    for t in ["flood", "cyclone", "earthquake", "landslide", "fire"]:
                        if t in combined:
                            hint = t.capitalize()
                            break
                    
                    posts.append({
                        "id": f"rss_{uuid.uuid4().hex[:8]}",
                        "text": summary or title,
                        "title": title,
                        "url": entry.link,
                        "image_url": None,
                        "source": "rss",
                        "timestamp": entry.get("published", datetime.now().isoformat()),
                        "score": 40,
                        "disaster_hint": hint
                    })
        except Exception as e:
            logger.warning(f"Failed to scrape RSS {url}: {e}")
    return posts

def load_simulated() -> list[dict]:
    """Load simulated posts as safety net."""
    posts = []
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "data", "simulated_posts.json")
        with open(path, "r") as f:
            posts = json.load(f)
            
        # Update timestamps to be recent relative to now
        base_time = datetime.now()
        for i, p in enumerate(posts):
            p["timestamp"] = (base_time - timedelta(minutes=i*2)).isoformat()
            
    except Exception as e:
        logger.error(f"Failed to load simulated posts: {e}")
    return posts

def merge_and_deduplicate(all_posts: list[dict]) -> list[dict]:
    """Merge and remove duplicates by URL."""
    seen_urls = set()
    merged = []
    for p in all_posts:
        url = p.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(p)
        elif not url:
            merged.append(p)
            
    merged.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return merged

def scrape_all() -> list[dict]:
    """Run all scrapers and combine results."""
    logger.info("Starting data collection...")
    all_posts = []
    
    gdacs_posts = scrape_gdacs()
    rw_posts = scrape_reliefweb()
    bsky_posts = scrape_bluesky()
    rss_posts = scrape_rss()
    sim_posts = load_simulated()
    
    logger.info(f"GDACS: {len(gdacs_posts)}, ReliefWeb: {len(rw_posts)}, "
                f"Bluesky: {len(bsky_posts)}, RSS: {len(rss_posts)}, "
                f"Simulated: {len(sim_posts)}")
                
    all_posts.extend(gdacs_posts)
    all_posts.extend(rw_posts)
    all_posts.extend(bsky_posts)
    all_posts.extend(rss_posts)
    all_posts.extend(sim_posts) # Never skip simulated
    
    merged = merge_and_deduplicate(all_posts)
    logger.info(f"Total unique posts collected: {len(merged)}")
    return merged
