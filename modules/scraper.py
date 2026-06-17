"""
modules/scraper.py — Web scraping for all 3 channels.

Uses:
  - requests + BeautifulSoup4 for static pages
  - Playwright for JavaScript-rendered pages
  - Reddit JSON API for subreddit scraping

Each channel has a tailored extraction strategy.
"""

import json
import time
import random
from typing import Optional

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from config import SCRAPE_SOURCES, API_RATE_LIMIT_SLEEP, DATA_DIR
from modules.logger import get_logger

log = get_logger("scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Reddit requires a specific user-agent format to allow API access
REDDIT_HEADERS = {
    "User-Agent": "ShortForge/1.0 (content scraper; contact: admin@shortforge.ai)",
    "Accept": "application/json",
}


class ContentScraper:
    """Scrapes story/topic content for a given channel."""

    def __init__(self, channel: str):
        self.channel = channel
        self.sources = SCRAPE_SOURCES.get(channel, [])

    # ─── Public API ──────────────────────────────────────────────────────────
    def scrape_month(self, count: int = 60) -> list[dict]:
        """Scrape `count` stories for this channel."""
        history_file = DATA_DIR / f"history_{self.channel}.json"
        
        # Load historical titles to prevent cross-run repeats
        history = set()
        if history_file.exists():
            try:
                history = set(json.loads(history_file.read_text()))
            except Exception:
                pass

        stories = []
        for source_url in self.sources:
            if len(stories) >= count * 2:  # Buffer extra to account for drops
                break
            try:
                batch = self._scrape_source(source_url)
                # Filter against historical repeats
                for s in batch:
                    key = s.get("title", "")[:80].strip().lower()
                    if key and key not in history:
                        stories.append(s)
                log.info(f"[{self.channel}] Scraped {len(batch)} from {source_url}")
            except Exception as e:
                log.warning(f"[{self.channel}] Failed {source_url}: {e}")
            time.sleep(API_RATE_LIMIT_SLEEP + random.uniform(0.5, 1.5))

        # Deduplicate within current batch
        seen = set()
        unique = []
        for s in stories:
            key = s.get("title", "")[:80].strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(s)

        final_batch = unique[:count]

        # Save new titles to history
        for s in final_batch:
            history.add(s.get("title", "")[:80].strip().lower())
        
        history_file.write_text(json.dumps(list(history)))

        log.info(f"[{self.channel}] Total unique stories (new): {len(final_batch)}")
        return final_batch

    # ─── Routing ─────────────────────────────────────────────────────────────
    def _scrape_source(self, url: str) -> list[dict]:
        if "reddit.com" in url and (".json" in url):
            return self._scrape_reddit(url)
        elif "aesopfables.com" in url:
            return self._scrape_aesop(url)
        elif "gutenberg.org" in url:
            return self._scrape_gutenberg(url)
        else:
            return self._scrape_generic(url)

    # ─── Reddit JSON API (via Playwright) ────────────────────────────────────
    def _scrape_reddit(self, url: str) -> list[dict]:
        log.info(f"[{self.channel}] Using Playwright to bypass Reddit JS challenge for {url}")
        
        with sync_playwright() as p:
            # Launch in headless mode, but look like a real browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Reddit JSON is usually wrapped in a <pre> tag when viewed in a browser
                content = page.locator("pre").inner_text(timeout=5000)
            except Exception:
                # Fallback if no <pre> tag is found
                content = page.locator("body").inner_text()
                
            browser.close()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            log.error(f"[{self.channel}] Failed to parse Reddit JSON. Raw content snippet: {content[:200]}")
            raise ValueError("Reddit returned non-JSON content (likely blocked or CAPTCHA).")

        posts = data.get("data", {}).get("children", [])
        results = []
        for post in posts:
            p = post.get("data", {})
            if p.get("is_self") and p.get("selftext"):
                results.append({
                    "title": p.get("title", ""),
                    "summary": p.get("selftext", "")[:1000],
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "score": p.get("score", 0),
                    "source": "reddit",
                    "channel": self.channel,
                })
            elif p.get("title"):
                results.append({
                    "title": p.get("title", ""),
                    "summary": p.get("title", ""),
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "score": p.get("score", 0),
                    "source": "reddit",
                    "channel": self.channel,
                })
        return results

    # ─── Generic static HTML scraper ─────────────────────────────────────────
    def _scrape_generic(self, url: str) -> list[dict]:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        # Try to extract articles/headlines
        for tag in soup.find_all(["article", "div"], class_=lambda c: c and
                                  any(x in c.lower() for x in ["article", "post", "story", "card"])):
            title_el = tag.find(["h1", "h2", "h3", "h4"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 10:
                continue

            # Get summary from first paragraph
            para = tag.find("p")
            summary = para.get_text(strip=True)[:500] if para else title

            # Get link
            link = tag.find("a", href=True)
            href = link["href"] if link else url
            if href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"

            results.append({
                "title": title,
                "summary": summary,
                "url": href,
                "source": url,
                "channel": self.channel,
            })

        return results

    # ─── Aesop Fables ────────────────────────────────────────────────────────
    def _scrape_aesop(self, url: str) -> list[dict]:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for link in soup.find_all("a", href=True):
            if "/cgi/aesop1.cgi" in link["href"] or "fable" in link["href"].lower():
                title = link.get_text(strip=True)
                if len(title) > 5:
                    results.append({
                        "title": title,
                        "summary": f"Aesop fable: {title}",
                        "url": link["href"] if link["href"].startswith("http") else f"https://www.aesopfables.com{link['href']}",
                        "source": "aesopfables.com",
                        "channel": self.channel,
                        "moral": "",  # Will be filled by Cerebras
                    })
        return results

    # ─── Project Gutenberg ───────────────────────────────────────────────────
    def _scrape_gutenberg(self, url: str) -> list[dict]:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/ebooks/" in href:
                title = link.get_text(strip=True)
                if len(title) > 5:
                    full_url = f"https://www.gutenberg.org{href}" if href.startswith("/") else href
                    results.append({
                        "title": title,
                        "summary": f"Classic story: {title}",
                        "url": full_url,
                        "source": "gutenberg.org",
                        "channel": self.channel,
                    })
        return results

    # ─── Playwright (dynamic pages) ──────────────────────────────────────────
    @staticmethod
    async def scrape_dynamic(url: str) -> str:
        """Scrape JS-rendered pages. Returns page HTML as string."""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_extra_http_headers(HEADERS)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            content = await page.content()
            await browser.close()
        return content
