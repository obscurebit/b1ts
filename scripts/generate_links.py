#!/usr/bin/env python3
"""
Generate daily obscure links for Obscure Bit - Version 2.

This script implements an improved link generation pipeline:
1. Search the web for candidate URLs based on theme
2. Scrape content from each URL
3. Verify relevance to theme using LLM analysis
4. Score based on relevance + obscurity
5. Return curated list of best links
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import random
import time

import yaml
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# Import our web scraper
from web_scraper import WebScraper, ScrapedContent

# Configuration
API_BASE = os.environ.get("OPENAI_API_BASE", "https://integrate.api.nvidia.com/v1")
API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = os.environ.get("OPENAI_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1.5")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
CONTEXTUALWEB_API_KEY = os.environ.get("CONTEXTUALWEB_API_KEY")

# Paths
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "links_system.md"
THEMES_FILE = PROMPTS_DIR / "themes.yaml"
CACHE_DIR = Path("cache/link_generation")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Search configuration
SEARCH_TIMEOUT = 15
MAX_CANDIDATES = 40
MIN_RELEVANCE_SCORE = 0.5
MIN_OBSCURITY_SCORE = 0.3
MIN_RELEVANCE_FALLBACK = 0.35
MIN_OBSCURITY_FALLBACK = 0.25
MINIMUM_SELECTED_LINKS = 3
MIN_LLM_DOMAIN_IDEAS = 3
MIN_LLM_SEARCH_QUERIES = 3

DDG_MAX_RETRIES = 3
DDG_MIN_INTERVAL = 1.0  # seconds between requests
DDG_THROTTLE_FACTOR = 1.5
DDG_DISABLE_AFTER_FAILURES = 3  # queries
DDG_USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/121.0'
]

THINKING_BLOCK_RE = re.compile(r'^<think>.*?</think>\s*', re.S)
DISALLOWED_BASE_DOMAINS = ("wikipedia.org", "archive.org", "github.com")


_last_ddg_request_time = 0.0
_ddg_failure_count = 0
_ddg_disabled_for_run = False


def _throttle_ddg(min_interval: float) -> None:
    """Ensure we respect a minimum interval between DuckDuckGo requests."""
    global _last_ddg_request_time
    now = time.time()
    wait = min_interval - (now - _last_ddg_request_time)
    if wait > 0:
        time.sleep(wait)
    _last_ddg_request_time = time.time()


def _reset_ddg_state() -> None:
    global _ddg_failure_count, _ddg_disabled_for_run
    _ddg_failure_count = 0
    _ddg_disabled_for_run = False


def _record_ddg_success() -> None:
    global _ddg_failure_count
    _ddg_failure_count = 0


def _record_ddg_failure() -> None:
    global _ddg_failure_count, _ddg_disabled_for_run
    _ddg_failure_count += 1
    if not _ddg_disabled_for_run and _ddg_failure_count >= DDG_DISABLE_AFTER_FAILURES:
        _ddg_disabled_for_run = True
        print("      ⚠️  Disabling DuckDuckGo for the remainder of this run (3 failed queries)")


def load_system_prompt() -> str:
    """Load the system prompt from external file."""
    if not SYSTEM_PROMPT_FILE.exists():
        return "You are a helpful assistant that finds obscure and interesting web links."
    return SYSTEM_PROMPT_FILE.read_text().strip()


RESEARCH_STRATEGY_PROMPT_FILE = PROMPTS_DIR / "research_strategy_system.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate curated obscure links")
    parser.add_argument("--theme-json", help="JSON string or path to JSON file specifying today's theme")
    return parser.parse_args()


def load_theme_override(raw_value: Optional[str]) -> Optional[dict]:
    source = raw_value or os.environ.get("THEME_JSON")
    if not source:
        return None
    try:
        text = source.strip()
        if text.startswith("{"):
            data = json.loads(text)
        else:
            potential = Path(text)
            if potential.exists():
                data = json.loads(potential.read_text())
            else:
                data = json.loads(text)
        print(f"Using theme override: {data.get('name', 'custom')}")
        return data
    except Exception as e:
        print(f"⚠️  Failed to parse theme override: {e}")
        return None

def load_research_strategy_prompt() -> str:
    """Load the research strategy system prompt from external file."""
    if not RESEARCH_STRATEGY_PROMPT_FILE.exists():
        return "You are a research strategist. Suggest domain ideas and search queries."
    return RESEARCH_STRATEGY_PROMPT_FILE.read_text().strip()


def strip_thinking_block(content: str) -> str:
    """Remove leading <think> blocks the model may include."""
    if not content:
        return ""
    return THINKING_BLOCK_RE.sub("", content, count=1).strip()


def is_disallowed_domain(domain: str) -> bool:
    domain = domain.lower()
    if domain.endswith('.edu'):
        return True
    return any(domain == base or domain.endswith(f".{base}") for base in DISALLOWED_BASE_DOMAINS)


def normalize_search_query(query: str) -> Optional[str]:
    if not query:
        return None
    clean = query.strip().strip('"').strip("'")
    clean = re.sub(r'\s+', ' ', clean)
    if len(clean) < 5:
        return None
    # Require at least 3 alphabetic characters
    if sum(1 for c in clean if c.isalpha()) < 3:
        return None
    return clean


def sanitize_llm_list(items: List[str]) -> List[str]:
    cleaned = []
    seen = set()
    for raw in items:
        if not raw:
            continue
        text = raw.strip().strip('-').strip()
        if len(text) < 6:
            continue
        if re.fullmatch(r'[\.0-9]+', text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def looks_like_boilerplate(candidate: "LinkCandidate") -> bool:
    """Detect obvious low-value pages like contact/privacy/careers."""
    url = candidate.url.lower()
    title = (candidate.title or "").lower()
    description = (candidate.description or "").lower()
    content = (candidate.content or "")[:400].lower()
    boiler_keywords = [
        "contact", "privacy", "terms", "legal", "copyright", "careers",
        "login", "signup", "subscribe", "newsletter", "cookies", "policy",
        "advertise", "sponsorship", "about us", "our team", "press media"
    ]
    if any(k in url for k in boiler_keywords):
        return True
    combined = " ".join([title, description, content])
    hits = sum(1 for k in boiler_keywords if k in combined)
    if hits >= 2:
        return True
    # Extremely short or generic content
    if len(candidate.content) < 600 and hits >= 1:
        return True
    return False


def ensure_minimum_entries(primary: List[str], backups: List[str], minimum: int) -> List[str]:
    merged = []
    seen = set()
    for item in primary + backups:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= minimum:
            break
    return merged


def search_marginalia(query: str, max_results: int = 8) -> List[str]:
    """Fallback search using Marginalia (indie search engine)."""
    clean_query = query.strip()
    if not clean_query:
        return []
    headers = {
        'User-Agent': random.choice(DDG_USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    try:
        response = requests.get(
            "https://search.marginalia.nu/search",
            params={"query": clean_query},
            headers=headers,
            timeout=SEARCH_TIMEOUT,
        )
        if response.status_code != 200:
            print(f"      ⚠️  Marginalia status {response.status_code}")
            return []
        soup = BeautifulSoup(response.text, 'html.parser')
        urls = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if href.startswith('http') and 'marginalia.nu' not in href:
                urls.append(href)
        seen = set()
        clean = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                clean.append(url)
        if clean:
            print(f"      ✅ Marginalia fallback returned {len(clean)} URLs")
        return clean[:max_results]
    except Exception as e:
        print(f"      ⚠️  Marginalia fallback failed: {e}")
        return []


def generate_backup_domain_ideas(theme_name: str, links_direction: str) -> List[str]:
    base = theme_name.lower()
    direction = links_direction.lower()
    return [
        f"Recovered personal diaries describing {base} moments hidden in {direction} collections.",
        f"Technical excavation logs from hobbyists restoring {base} artifacts tied to {direction} history.",
        f"Museum or community oral histories documenting {base} through {direction} field work.",
        f"Investigations into lost or shuttered projects where {base} research went missing within {direction} archives.",
        f"Independent labs experimenting with preserving {base} materials discovered via {direction} leads.",
    ]


def generate_backup_search_queries(theme_name: str, links_direction: str) -> List[str]:
    combos = [
        f'"{theme_name}" "field notes" {links_direction}',
        f'{theme_name} "case study" intitle:"archives" -wikipedia',
        f'"{theme_name}" "primary source" {links_direction}',
        f'{theme_name} "artifact" "personal blog"',
        f'{theme_name} "museum report" "obscure"',
    ]
    return combos


def filter_llm_urls(urls: List[str]) -> List[str]:
    filtered = []
    seen = set()
    for url in urls:
        try:
            parsed = urlparse(url)
        except Exception:
            continue
        domain = parsed.netloc.lower()
        if not domain or is_disallowed_domain(domain):
            continue
        if url in seen:
            continue
        seen.add(url)
        filtered.append(url)
    return filtered[:5]


def load_themes() -> dict:
    """Load unified themes configuration from YAML file."""
    if not THEMES_FILE.exists():
        print(f"Error: Themes file not found at {THEMES_FILE}")
        sys.exit(1)
    return yaml.safe_load(THEMES_FILE.read_text()) or {}


def get_daily_theme() -> dict:
    """Get today's theme (story + links directions)."""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    day_of_year = today.timetuple().tm_yday
    
    config = load_themes()
    
    # Check for date-specific override
    overrides = config.get("overrides", {})
    if date_str in overrides:
        theme = overrides[date_str]
        print(f"Using theme override for {date_str}: {theme.get('name', 'custom')}")
        return theme
    
    # Use rotating themes
    themes = config.get("themes", [])
    if not themes:
        print("Error: No themes found in themes.yaml")
        sys.exit(1)
    
    theme = themes[day_of_year % len(themes)]
    print(f"Using theme: {theme.get('name', 'unknown')}")
    return theme


class LinkCandidate:
    """Represents a potential link with its metadata and scores."""
    def __init__(self, url: str, title: str = "", description: str = ""):
        self.url = url
        self.title = title
        self.description = description
        self.content = ""
        self.concepts: List[str] = []
        self.relevance_score = 0.0
        self.obscurity_score = 0.0
        self.final_score = 0.0
        self.error: Optional[str] = None
        
    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "relevance_score": self.relevance_score,
            "obscurity_score": self.obscurity_score,
            "final_score": self.final_score,
            "concepts": self.concepts[:5],
        }


def search_duckduckgo(query: str, max_results: int = 10) -> List[str]:
    """Search DuckDuckGo Lite with throttling/retries and parse direct/redirect URLs."""
    if not query:
        return []

    clean_query = query.strip().strip('"').strip("'")

    global _ddg_disabled_for_run
    if _ddg_disabled_for_run:
        print("      ⚠️  DuckDuckGo disabled for this run; skipping query")
        return search_marginalia(clean_query, max_results=max_results)

    for attempt in range(DDG_MAX_RETRIES):
        headers = {
            'User-Agent': random.choice(DDG_USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.8',
            'Referer': 'https://duckduckgo.com/',
        }
        delay = DDG_MIN_INTERVAL * (DDG_THROTTLE_FACTOR ** attempt)
        _throttle_ddg(delay)
        try:
            session = requests.Session()
            session.headers.update(headers)
            endpoints = [
                ("post", "https://lite.duckduckgo.com/lite/", {'q': clean_query, 'kl': 'us-en'}),
                ("get", f"https://lite.duckduckgo.com/lite/?q={quote_plus(clean_query)}&kl=us-en", None),
                ("get", f"https://duckduckgo.com/html/?q={quote_plus(clean_query)}&ia=web", None),
            ]

            response = None
            for method, url, data in endpoints:
                print(f"      🔍 DDG: {clean_query[:60]}... ({method.upper()} {url.split('//')[1][:30]}...) (attempt {attempt + 1})")
                if method == "post":
                    response = session.post(url, data=data, timeout=SEARCH_TIMEOUT, allow_redirects=True)
                else:
                    response = session.get(url, timeout=SEARCH_TIMEOUT, allow_redirects=True)
                print(f"      📄 Status: {response.status_code}")
                if response.status_code in (200, 202):
                    break
                if response.status_code == 429:
                    print("      ⚠️  DDG rate-limited (429). Backing off...")
                    time.sleep(2)
                elif response.status_code == 403:
                    print("      ⚠️  DDG returned 403 (blocked). Trying alternate endpoint...")
                else:
                    print(f"      ⚠️  DDG unexpected status {response.status_code}")
                response = None

            if not response:
                continue

            if response.status_code == 202:
                print("      ⚠️  DDG returned 202 (throttled). Waiting and retrying...")
                time.sleep(1)
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            raw_urls = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                candidate = None
                if href.startswith('http') and 'duckduckgo.com' not in href:
                    candidate = href
                elif 'uddg=' in href:
                    parsed = urlparse(href)
                    params = parse_qs(parsed.query)
                    redirect = params.get('uddg', [None])[0]
                    if redirect:
                        candidate = unquote(redirect)

                if candidate and candidate.startswith('http'):
                    raw_urls.append(candidate)

            print(f"      🔗 Found {len(raw_urls)} URLs")
            for i, url in enumerate(raw_urls[:3], 1):
                print(f"         {i}. {url[:60]}...")

            skip_domains = {'duckduckgo.com', 'google.com', 'bing.com', 'facebook.com',
                            'twitter.com', 'instagram.com', 'youtube.com'}
            seen = set()
            clean_urls = []
            for url in raw_urls:
                domain = urlparse(url).netloc.lower()
                if any(skip in domain for skip in skip_domains):
                    continue
                if url not in seen:
                    seen.add(url)
                    clean_urls.append(url)

            print(f"      ✅ Cleaned to {len(clean_urls)} unique")
            if clean_urls:
                _record_ddg_success()
                return clean_urls[:max_results]

        except Exception as e:
            print(f"      ❌ DDG failed (attempt {attempt + 1}): {e}")

    _record_ddg_failure()
    print("      ❌ DDG exhausted retries with no results")
    fallback = search_marginalia(clean_query, max_results=max_results)
    return fallback


def search_academic_sources(theme: str, links_direction: str) -> List[str]:
    """Search academic and archival sources for relevant content."""
    urls = []
    
    # Build search terms
    terms = f"{theme} {links_direction}"
    query = quote_plus(terms)
    
    # arXiv search
    try:
        arxiv_url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results=5"
        response = requests.get(arxiv_url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            # Parse arXiv IDs from XML
            ids = re.findall(r'<id>(http://arxiv.org/abs/\d+\.\d+)</id>', response.text)
            urls.extend(ids)
            print(f"  Found {len(ids)} results from arXiv")
    except Exception as e:
        print(f"  arXiv search failed: {e}")
    
    # Archive.org search
    try:
        archive_url = f"https://archive.org/advancedsearch.php?q={query}&output=json&rows=5"
        response = requests.get(archive_url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            docs = data.get('response', {}).get('docs', [])
            for doc in docs:
                identifier = doc.get('identifier')
                if identifier:
                    urls.append(f"https://archive.org/details/{identifier}")
            print(f"  Found {len(docs)} results from Archive.org")
    except Exception as e:
        print(f"  Archive.org search failed: {e}")
    
    return urls


def search_extended_sources(theme: str, links_direction: str) -> List[str]:
    """Search 30+ extended sources for obscure content."""
    urls = []
    query = quote_plus(f"{theme} {links_direction}")
    
    # === ACADEMIC & RESEARCH (8 sources) ===
    academic_sources = [
        # Google Scholar
        ("https://scholar.google.com/scholar?q={q}", "Google Scholar"),
        # Semantic Scholar
        ("https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=5", "Semantic Scholar"),
        # CORE (Open Access Research)
        ("https://core.ac.uk/api-v2/articles/search/{q}?apiKey=dummy&page=1&pageSize=5", "CORE"),
        # BASE (Bielefeld Academic Search)
        ("https://base-search.net/Search/Results?lookfor={q}&type=all&limit=5", "BASE"),
        # PubMed (medical/biological)
        ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={q}&retmax=5&retmode=json", "PubMed"),
        # DOAJ (Open Access Journals)
        ("https://doaj.org/api/search/articles/{q}?pageSize=5", "DOAJ"),
        # SSRN (Social Science)
        ("https://www.ssrn.com/index.cfm/en/search/?searchText={q}", "SSRN"),
        # JSTOR (for older papers - limited access)
        ("https://www.jstor.org/action/doBasicSearch?Query={q}&acc=off&wc=on&fc=off&group=none", "JSTOR"),
    ]
    
    # === DIGITAL ARCHIVES & LIBRARIES (10 sources) ===
    archive_sources = [
        # HathiTrust
        ("https://catalog.hathitrust.org/api/volumes/full/json?q={q}", "HathiTrust"),
        # Digital Public Library of America
        ("https://api.dp.la/v2/items?q={q}&api_key=dummy&page_size=5", "DPLA"),
        # Library of Congress
        ("https://www.loc.gov/search/?q={q}&fo=json&c=5", "Library of Congress"),
        # National Archives
        ("https://catalog.archives.gov/api/v1?rows=5&q={q}", "National Archives"),
        # Europeana
        ("https://api.europeana.eu/record/v2/search.json?wskey=dummy&query={q}&rows=5", "Europeana"),
        # Gallica (French digital library)
        ("https://gallica.bnf.fr/services/engine/search/sru?operation=searchRetrieve&query={q}&maximumRecords=5", "Gallica"),
        # Trove (Australia)
        ("https://trove.nla.gov.au/api/result?q={q}&zone=all&n=5&encoding=json", "Trove"),
        # Wellcome Collection (medical history)
        ("https://api.wellcomecollection.org/catalogue/v2/works?query={q}&pageSize=5", "Wellcome"),
        # Smithsonian
        ("https://api.si.edu/openaccess/api/v1.0/search?q={q}&rows=5", "Smithsonian"),
        # Digital Commons Network
        ("https://network.bepress.com/cgi/query.cgi?query={q}", "Digital Commons"),
    ]
    
    # === TECH/COMPUTING HISTORY (6 sources) ===
    tech_sources = [
        # GitHub search (for abandoned projects)
        ("https://api.github.com/search/repositories?q={q}+stars:<10+updated:<2020-01-01&sort=updated&order=desc&per_page=5", "GitHub"),
        # Computer History Museum
        ("https://www.computerhistory.org/search/?q={q}", "Computer History Museum"),
        # Bitsavers (computer documentation)
        ("http://bitsavers.org/search.html?q={q}", "Bitsavers"),
        # Vintage Computing Federation
        ("https://vcfed.org/search/?q={q}", "VCF"),
        # Textfiles.com (BBS era)
        ("http://textfiles.com/search/?q={q}", "Textfiles"),
        # Software Heritage
        ("https://archive.softwareheritage.org/browse/search/?q={q}", "Software Heritage"),
    ]
    
    # === SPECIALIZED/CURATED PLATFORMS (8 sources) ===
    curated_sources = [
        # Are.na (curated collections)
        ("https://api.are.na/v2/search?q={q}&per=5", "Are.na"),
        # Atlas Obscura
        ("https://www.atlasobscura.com/search?query={q}", "Atlas Obscura"),
        # Reddit (obscure subreddits via search)
        ("https://www.reddit.com/search/?q={q}&type=posts&sort=relevance&t=all", "Reddit"),
        # Hacker News (Algolia API)
        ("http://hn.algolia.com/api/v1/search?query={q}&tags=(story,show_hn)&hitsPerPage=5", "Hacker News"),
        # Metafilter
        ("https://www.metafilter.com/search.mefi?site=mefi&q={q}", "Metafilter"),
        # 99% Invisible
        ("https://99percentinvisible.org/?s={q}", "99PI"),
        # Public Domain Review
        ("https://publicdomainreview.org/?s={q}", "Public Domain Review"),
        # Wikipedia "Further reading" via search
        ("https://en.wikipedia.org/w/api.php?action=opensearch&search={q}&limit=5&namespace=0&format=json", "Wikipedia"),
    ]
    
    # === GOVERNMENT/INSTITUTIONAL (5 sources) ===
    gov_sources = [
        # NASA Technical Reports
        ("https://ntrs.nasa.gov/api/search?q={q}&page=1&size=5", "NASA NTRS"),
        # USPTO Patents
        ("https://patentsview.uspto.gov/api/patents/query?q={{\"_and\":{{\"_text_any\":{{\"patent_title\":\"{q}\"}}}}}}&f=[\"patent_number\",\"patent_title\"]&o={{\"per_page\":5}}", "USPTO"),
        # DOE OSTI
        ("https://www.osti.gov/api/v1/records?q={q}&rows=5", "OSTI"),
        # DTIC (Defense Technical)
        ("https://discover.dtic.mil/wp-json/dtic/v1/search?q={q}&posts_per_page=5", "DTIC"),
        # CIA FOIA Reading Room
        ("https://www.cia.gov/readingroom/search/site/{q}", "CIA FOIA"),
    ]
    
    # === SPECIALIZED SEARCH ENGINES (5 sources) ===
    # These surface obscure, non-commercial content perfect for discovery
    obscure_sources = [
        # Million Short - removes top 1M sites, surfaces hidden gems
        ("https://millionshort.com/search?q={q}&remove=1000000", "Million Short"),
        # Marginalia - indie search for old/forgotten web pages
        ("https://search.marginalia.nu/search?query={q}", "Marginalia"),
        # Open Library - millions of books, rare/out-of-print
        ("https://openlibrary.org/search.json?q={q}&limit=5", "Open Library"),
        # WorldCat - global library catalog (2B+ items)
        ("https://www.worldcat.org/search?q={q}", "WorldCat"),
        # Stanford Web Archive Portal - curated historical collections
        ("https://swap.stanford.edu/?q={q}", "Stanford Web Archive"),
    ]
    
    all_sources = (
        [("academic", url, name) for url, name in academic_sources] +
        [("archive", url, name) for url, name in archive_sources] +
        [("tech", url, name) for url, name in tech_sources] +
        [("curated", url, name) for url, name in curated_sources] +
        [("gov", url, name) for url, name in gov_sources] +
        [("obscure", url, name) for url, name in obscure_sources]
    )
    
    print(f"\n  Searching 42 extended sources...")
    
    # Sample 20 sources to broaden coverage (rotating selection)
    random.shuffle(all_sources)
    selected_sources = all_sources[:20]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    
    for category, url_template, name in selected_sources:
        try:
            url = url_template.format(q=query)
            response = requests.get(url, headers=headers, timeout=8)
            
            if response.status_code == 200:
                # Extract URLs based on response type
                found_urls = extract_urls_from_response(response, name, category)
                if found_urls:
                    urls.extend(found_urls[:3])  # Max 3 per source to widen pool
                    print(f"    ✓ {name}: {len(found_urls)} found")
            
        except Exception as e:
            # Silent fail for individual sources
            pass
    
    # Remove duplicates
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    print(f"  Total unique from extended sources: {len(unique_urls)}")
    return unique_urls


def run_operator_queries(theme: str, links_direction: str) -> List[str]:
    """Run additional DDG queries with search operators to expand candidate pool."""
    operator_queries = [
        f'"{theme}" "field notes" -site:.edu -site:wikipedia.org',
        f'"{theme}" "{links_direction}" intitle:"case study" -list -site:wikipedia.org',
        f'"{theme}" filetype:pdf "report" -site:.edu -site:archive.org',
        f'"{theme}" "personal blog" "lost" -site:wikipedia.org -site:medium.com',
    ]

    all_urls = []
    print("\n  Running operator-driven searches...")
    for query in operator_queries:
        print(f"    Query: {query[:80]}...")
        results = search_duckduckgo(query, max_results=5)
        all_urls.extend(results)
        if results:
            print(f"      Found {len(results)} URLs")
    return all_urls


def run_fallback_searches(theme: str, links_direction: str) -> List[str]:
    """Query a curated list of dependable sources plus generic backups."""
    fallback_sources = [
        ("Library of Congress", 'site:loc.gov "{theme}" "{direction}"'),
        ("Smithsonian Magazine", 'site:smithsonianmag.com "{theme}"'),
        ("Foreign Affairs", 'site:foreignaffairs.com "{theme}"'),
        ("Cold War International History Project", 'site:wilsoncenter.org "{theme}"'),
        ("National Security Archive", 'site:gwu.edu "National Security Archive" "{theme}"'),
        ("NASA History", 'site:nasa.gov history "{theme}"'),
        ("Intelligence.org", 'site:intelligence.org "{theme}"'),
        ("Britannica", 'site:britannica.com "{theme}" "{direction}" -list'),
    ]

    extra_queries = [
        f'"{theme}" "{links_direction}" "oral history"',
        f'"{theme}" "{links_direction}" "archives" -site:wikipedia.org',
        f'"{theme}" "{links_direction}" "personal diary"',
        f'"{theme}" "{links_direction}" "declassified"',
    ]

    collected: List[str] = []

    for label, template in fallback_sources:
        query = template.format(theme=theme, direction=links_direction)
        print(f"\n  Fallback search ({label})...")
        ddg_results = search_duckduckgo(query, max_results=4)
        collected.extend(ddg_results)
        if not ddg_results:
            marginalia_results = search_marginalia(query, max_results=3)
            collected.extend(marginalia_results)

    print("\n  Fallback generic queries...")
    for query in extra_queries:
        print(f"    Query: {query[:80]}...")
        results = search_duckduckgo(query, max_results=4)
        collected.extend(results)
        if not results:
            collected.extend(search_marginalia(query, max_results=3))

    seen = set()
    unique_urls = []
    for url in collected:
        if not url or url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)

    print(f"  Fallback sources contributed {len(unique_urls)} URLs")
    return unique_urls


def _filter_external_urls(urls: List[str]) -> List[str]:
    """Deduplicate and filter disallowed domains for API-based search results."""
    filtered = []
    seen = set()
    for url in urls:
        if not url:
            continue
        try:
            domain = urlparse(url).netloc.lower()
        except Exception:
            continue
        if not domain or is_disallowed_domain(domain):
            continue
        if url in seen:
            continue
        seen.add(url)
        filtered.append(url)
    return filtered


def search_serpapi(query: str, max_results: int = 8) -> List[str]:
    """Use SerpApi (if configured) to fetch additional web results."""
    if not SERPAPI_KEY:
        return []
    try:
        params = {
            "engine": "google",
            "q": query,
            "num": max_results,
            "api_key": SERPAPI_KEY,
        }
        response = requests.get("https://serpapi.com/search", params=params, timeout=SEARCH_TIMEOUT)
        if response.status_code != 200:
            print(f"    ⚠️  SerpApi status {response.status_code}")
            return []
        data = response.json()
        urls = [item.get("link") for item in data.get("organic_results", []) if item.get("link")]
        return _filter_external_urls(urls)[:max_results]
    except Exception as e:
        print(f"    ⚠️  SerpApi request failed: {e}")
        return []


def search_contextualweb(query: str, max_results: int = 8) -> List[str]:
    """Use ContextualWeb Search (RapidAPI) if configured."""
    if not CONTEXTUALWEB_API_KEY:
        return []
    try:
        headers = {
            "X-RapidAPI-Key": CONTEXTUALWEB_API_KEY,
            "X-RapidAPI-Host": "contextualwebsearch-websearch-v1.p.rapidapi.com",
        }
        params = {
            "q": query,
            "pageNumber": 1,
            "pageSize": max_results,
            "autoCorrect": "true",
            "safeSearch": "false",
        }
        response = requests.get(
            "https://contextualwebsearch-websearch-v1.p.rapidapi.com/api/Search/WebSearchAPI",
            headers=headers,
            params=params,
            timeout=SEARCH_TIMEOUT,
        )
        if response.status_code != 200:
            print(f"    ⚠️  ContextualWeb status {response.status_code}")
            return []
        data = response.json()
        urls = [item.get("url") for item in data.get("value", []) if item.get("url")]
        return _filter_external_urls(urls)[:max_results]
    except Exception as e:
        print(f"    ⚠️  ContextualWeb request failed: {e}")
        return []


def extract_urls_from_response(response: requests.Response, source_name: str, category: str) -> List[str]:
    """Extract URLs from various API responses."""
    urls = []
    
    try:
        # JSON APIs
        if 'json' in response.headers.get('Content-Type', ''):
            data = response.json()
            
            if source_name == "Semantic Scholar":
                papers = data.get('data', [])
                for p in papers:
                    if p.get('openAccessPdf', {}).get('url'):
                        urls.append(p['openAccessPdf']['url'])
                    elif p.get('externalIds', {}).get('DOI'):
                        urls.append(f"https://doi.org/{p['externalIds']['DOI']}")
            
            elif source_name in ["PubMed", "NASA NTRS", "OSTI", "DTIC"]:
                # Look for ID patterns in JSON
                if 'esearchresult' in str(data):  # PubMed
                    ids = data.get('esearchresult', {}).get('idlist', [])
                    for pmid in ids:
                        urls.append(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
                elif 'results' in data:  # NASA/OSTI
                    for r in data.get('results', [])[:3]:
                        if r.get('download'):
                            urls.append(r['download'])
                        elif r.get('links', [{}])[0].get('href'):
                            urls.append(r['links'][0]['href'])
            
            elif source_name == "Europeana":
                items = data.get('items', [])
                for item in items:
                    guid = item.get('guid')
                    if guid:
                        urls.append(guid)
            
            elif source_name == "Hacker News":
                hits = data.get('hits', [])
                for hit in hits:
                    url = hit.get('url')
                    if url and not url.startswith('http'):
                        url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                    if url:
                        urls.append(url)
            
            elif source_name == "Open Library":
                docs = data.get('docs', [])
                for doc in docs:
                    # Get Open Library work page
                    key = doc.get('key')
                    if key:
                        urls.append(f"https://openlibrary.org{key}")
                    # Or get archive.org link if available
                    ia_id = doc.get('ia', [None])[0]
                    if ia_id:
                        urls.append(f"https://archive.org/details/{ia_id}")
        
        # HTML responses - parse for links
        else:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract all external links
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if href.startswith('http') and not any(skip in href for skip in [
                    'google.com', 'facebook.com', 'twitter.com', 'instagram.com',
                    'youtube.com', 'linkedin.com', 'pinterest.com'
                ]):
                    urls.append(href.split('#')[0])
            
            # Specific parsers for certain sources
            if source_name == "Wikipedia":
                # Look for external link sections
                for extlink in soup.find_all('a', class_='external-text'):
                    href = extlink.get('href', '')
                    if href.startswith('http'):
                        urls.append(href)
            
            elif source_name == "Marginalia":
                # Marginalia shows results with original URLs
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if href.startswith('http') and 'marginalia.nu' not in href:
                        urls.append(href)
            
            elif source_name == "Million Short":
                # Million Short shows results from web
                for link in soup.find_all('a', class_=re.compile(r'result|title|url'), href=True):
                    href = link.get('href', '')
                    if href.startswith('http'):
                        urls.append(href)
            
            elif source_name == "WorldCat":
                # Look for catalog links
                for link in soup.find_all('a', href=re.compile(r'/title/')):
                    href = link.get('href', '')
                    if href.startswith('/'):
                        urls.append(f"https://www.worldcat.org{href}")
            
            elif source_name == "Stanford Web Archive":
                # Look for archived page links
                for link in soup.find_all('a', href=re.compile(r'web/\d{14}')):
                    href = link.get('href', '')
                    if href.startswith('http'):
                        urls.append(href)
    
    except Exception as e:
        pass
    
    return list(set(urls))[:5]  # Max 5 per source


def _extract_section(content: str, header: str, headers: List[str]) -> str:
    if header not in content:
        return ""
    after = content.split(f"{header}:", 1)[1]
    stops = []
    for other in headers:
        if other == header:
            continue
        marker = f"{other}:"
        idx = after.find(marker)
        if idx >= 0:
            stops.append(idx)
    if stops:
        after = after[:min(stops)]
    return after.strip()


def _parse_bulleted_text(text: str) -> List[str]:
    entries = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r'^[\-\*\d\.\)]+\s*', '', line).strip()
        if line:
            entries.append(line)
    return entries


def get_llm_research_strategy(theme: dict) -> Tuple[List[str], List[str], List[str]]:
    """Ask LLM for domain ideas, search queries, and direct URLs."""
    if not API_KEY:
        print("    ⚠️  No API key available")
        return [], [], []

    theme_name = theme.get("name", "")
    links_direction = theme.get("links", theme_name)

    system_prompt = load_research_strategy_prompt().format(
        theme_name=theme_name,
        links_direction=links_direction
    )

    headers = ["DOMAIN IDEAS", "SEARCH QUERIES", "URLs FOUND"]

    best_domain: List[str] = []
    best_queries: List[str] = []
    best_urls: List[str] = []

    for attempt in range(3):
        try:
            temperature = 0.45 + (attempt * 0.15)
            print(f"    🤖 LLM attempt {attempt + 1} (temp={temperature:.2f})")
            client = OpenAI(api_key=API_KEY, base_url=API_BASE)
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Research topic: {theme_name}"}
                ],
                temperature=temperature,
                max_tokens=1000
            )

            content = strip_thinking_block(response.choices[0].message.content or "")
            print(f"    📄 LLM output (first 300 chars): {content[:300]}...")

            raw_domain = _parse_bulleted_text(_extract_section(content, "DOMAIN IDEAS", headers))
            raw_queries = _parse_bulleted_text(_extract_section(content, "SEARCH QUERIES", headers))
            raw_urls = re.findall(r"https?://[^\s<>\"'\)\]\}]+", _extract_section(content, "URLs FOUND", headers) or content)

            best_domain = sanitize_llm_list(raw_domain)
            best_queries = [q for q in (normalize_search_query(q) for q in sanitize_llm_list(raw_queries)) if q]
            best_urls = filter_llm_urls(raw_urls)

            if len(best_domain) >= MIN_LLM_DOMAIN_IDEAS and len(best_queries) >= MIN_LLM_SEARCH_QUERIES:
                break

        except Exception as e:
            print(f"    LLM attempt {attempt + 1} failed: {e}")

    if len(best_domain) < MIN_LLM_DOMAIN_IDEAS:
        print("    ⚠️  Using backup domain ideas")
        best_domain = ensure_minimum_entries(best_domain, generate_backup_domain_ideas(theme_name, links_direction), MIN_LLM_DOMAIN_IDEAS)

    if len(best_queries) < MIN_LLM_SEARCH_QUERIES:
        print("    ⚠️  Using backup search queries")
        best_queries = ensure_minimum_entries(best_queries, generate_backup_search_queries(theme_name, links_direction), MIN_LLM_SEARCH_QUERIES)

    print(f"    ✅ LLM suggested {len(best_domain)} domain ideas")
    for i, idea in enumerate(best_domain[:3], 1):
        print(f"       {i}. {idea}")
    print(f"    ✅ LLM suggested {len(best_queries)} search queries")
    for i, query in enumerate(best_queries[:3], 1):
        print(f"       {i}. {query}")
    print(f"    ✅ LLM suggested {len(best_urls)} direct URLs")

    return best_domain, best_queries, best_urls


def get_llm_candidate_urls(theme: dict) -> List[str]:
    """Get URLs from LLM research strategy and follow-up searches."""
    _, search_queries, direct_urls = get_llm_research_strategy(theme)

    all_urls = list(direct_urls)

    if search_queries:
        print(f"\n  Executing LLM search queries...")
        for query in search_queries[:3]:
            print(f"    Query: {query[:80]}...")
            results = search_duckduckgo(query, max_results=5)
            all_urls.extend(results)
            if results:
                print(f"      Found {len(results)} from: {query[:60]}...")

    return all_urls[:15]


def get_llm_search_sources_batch(theme: dict, batch_num: int = 0) -> List[str]:
    """Ask LLM for domains - multiple batches."""
    if not API_KEY:
        return []
    
    theme_name = theme.get("name", "")
    
    prompts = [
        f"List 4 diverse website domains about {theme_name} (mix of news, history, tech, museums). Just domains:",
        f"List 4 different websites covering {theme_name} (not archive.org). Just domains:",
        f"List 4 varied sources for {theme_name} articles (blogs, news, edu, orgs). Just domains:",
    ]
    
    prompt = prompts[batch_num % len(prompts)]
    
    try:
        client = OpenAI(api_key=API_KEY, base_url=API_BASE)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4 + (batch_num * 0.1),
            max_tokens=200
        )
        
        content = response.choices[0].message.content
        domains = re.findall(r'[a-z0-9][a-z0-9\-\.]+\.(?:com|org|net|edu|io|co)', content.lower())
        
        return list(set(domains))
        
    except Exception as e:
        print(f"    Domain batch {batch_num} failed: {e}")
        return []


def get_llm_search_sources(theme: dict) -> List[str]:
    """Get domains from multiple LLM calls."""
    all_domains = []
    
    for i in range(3):  # 3 batches
        domains = get_llm_search_sources_batch(theme, i)
        all_domains.extend(domains)
        if domains:
            print(f"    Batch {i+1}: {len(domains)} domains")
    
    # Deduplicate
    seen = set()
    unique = []
    for d in all_domains:
        if d not in seen:
            seen.add(d)
            unique.append(d)
    
    print(f"    Total unique: {len(unique)} domains")
    return unique[:10]


def get_candidate_urls(theme: dict) -> List[str]:
    """Generate candidate URLs from multiple sources."""
    theme_name = theme.get("name", "")
    links_direction = theme.get("links", theme_name)
    
    print(f"\nTheme: {theme_name}")
    
    all_urls = []
    
    # 1. LLM suggestions (primary)
    print(f"\n  Getting LLM URL suggestions...")
    llm_urls = get_llm_candidate_urls(theme)
    all_urls.extend(llm_urls)
    
    # 2. Extended sources (42 different APIs and search engines)
    print(f"\n  Searching extended sources...")
    extended_urls = search_extended_sources(theme_name, links_direction)
    all_urls.extend(extended_urls)
    
    # 3. External API searches (SerpApi / ContextualWeb)
    search_terms = [
        f"{theme_name} {links_direction}",
        f"obscure {theme_name} history",
    ]
    api_urls = []
    if SERPAPI_KEY:
        print("\n  Querying SerpApi...")
        for term in search_terms:
            api_results = search_serpapi(term)
            api_urls.extend(api_results)
            if api_results:
                print(f"    SerpApi found {len(api_results)} for '{term[:40]}...'")
    if CONTEXTUALWEB_API_KEY:
        print("\n  Querying ContextualWeb...")
        for term in search_terms:
            api_results = search_contextualweb(term)
            api_urls.extend(api_results)
            if api_results:
                print(f"    ContextualWeb found {len(api_results)} for '{term[:40]}...'")
    all_urls.extend(api_urls)
    
    # 4. Operator-driven queries for extra breadth
    operator_urls = run_operator_queries(theme_name, links_direction)
    all_urls.extend(operator_urls)
    
    # 5. Ask LLM for diverse sources, then search them
    print(f"\n  Getting LLM source suggestions...")
    suggested_domains = get_llm_search_sources(theme)
    
    for domain in suggested_domains[:6]:  # search more domains for breadth
        print(f"\n  Searching DuckDuckGo (site:{domain})...")
        ddg_urls = search_duckduckgo(f"site:{domain} {theme_name}", max_results=6)
        all_urls.extend(ddg_urls)
    
    # 6. Fallback searches - curated list of reliable sources (no wikipedia/guardian duplicates)
    fallback_urls = run_fallback_searches(theme_name, links_direction)
    all_urls.extend(fallback_urls)

    # Deduplicate but keep order
    all_urls = list(dict.fromkeys(all_urls))

    if len(all_urls) < 25:
        print(f"\n  ⚠️  Only {len(all_urls)} unique candidates so far — running backup broad queries")
        booster_terms = [
            f"{theme_name} hidden history",
            f"forgotten {links_direction} archives",
            f"{theme_name} oral history",
        ]
        for term in booster_terms:
            ddg_results = search_duckduckgo(term, max_results=5)
            all_urls.extend(ddg_results)
            marginalia_results = search_marginalia(term, max_results=5)
            all_urls.extend(marginalia_results)
        all_urls = list(dict.fromkeys(all_urls))

    unique_urls = all_urls[:MAX_CANDIDATES]

    print(f"\nTotal unique candidates: {len(all_urls)}")
    return unique_urls


def search_archive_org(theme: str) -> List[str]:
    """Search Archive.org for specific items related to theme."""
    urls = []
    try:
        # Search for specific subjects in archive.org
        subjects = [
            f"{theme} invention",
            f"{theme} patent", 
            f"{theme} history",
            f"early {theme}",
        ]
        
        for subject in subjects[:2]:
            query = quote_plus(subject)
            # Use archive.org catalog search for items (not collections)
            search_url = f"https://archive.org/services/search/v1/scrape?fields=identifier,title&q={query}%20mediatype:texts&sorts=week"
            
            response = requests.get(search_url, timeout=SEARCH_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                docs = data.get('items', [])
                for doc in docs[:3]:  # Max 3 per subject
                    identifier = doc.get('identifier')
                    title = doc.get('title', '')
                    if identifier and title:
                        # Filter out generic collections
                        bad_keywords = ['collection', 'archive', 'library', 'group']
                        if not any(kw in title.lower() for kw in bad_keywords):
                            urls.append(f"https://archive.org/details/{identifier}")
                
        print(f"    Found {len(urls)} archive.org items")
    except Exception as e:
        print(f"    Archive.org search failed: {e}")
    
    return urls[:8]  # Return up to 8


def search_smithsonian(theme: str) -> List[str]:
    """Search Smithsonian API for specific objects."""
    urls = []
    try:
        # Smithsonian API
        query = quote_plus(f"{theme} invention")
        api_url = f"https://api.si.edu/openaccess/api/v1.0/search?q={query}&api_key=hJ1TEiyhGhY&rows=10"
        
        response = requests.get(api_url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            objects = data.get('response', {}).get('rows', [])
            for obj in objects:
                url = obj.get('content', {}).get('descriptiveNonRepeating', {}).get('online_media', {}).get('media', [{}])[0].get('guid')
                if not url:
                    url = f"https://www.si.edu/object/{obj.get('id')}"
                if url:
                    urls.append(url)
            print(f"    Found {len(urls)} Smithsonian items")
    except Exception as e:
        print(f"    Smithsonian search failed: {e}")
    
    return urls[:5]


def is_listicle_url(url: str, title: str = "") -> bool:
    """Detect if URL/title appears to be a listicle/junk article or collection."""
    listicle_patterns = [
        # Numbered listicles
        r'\d+\s+(forgotten|abandoned|obsolete|lost|hidden|secret|amazing|incredible|surprising|weird)',
        r'top\s+\d+',
        r'\d+\s+best',
        r'\d+\s+worst',
        r'\d+\s+things?\s+(you|to|that)',
        # List/collection content (even from academic sources)
        r'list\s+of',
        r'listicle',
        r'timeline\s+of',
        r'famous',
        r'notable',
        r'greatest',
        r'guide\s+to',
        r'research\s+guide',
        r'library\s+guide',
        r'collection\s+of',
        r'category:',
        r'index\s+of',
        # Clickbait sites
        r'listicle-site',
        r'buzzfeed',
        r'boredpanda',
        r'viralnova',
        r'ranker',
        r'list25',
        r'\d+-facts?',
        r'mind-blowing',
        r'will-blow-your-mind',
        r'you-won.t-believe',
        r'won.t-believe',
    ]
    
    combined_text = f"{url} {title}".lower()
    
    for pattern in listicle_patterns:
        if re.search(pattern, combined_text, re.IGNORECASE):
            return True
    
    # Check for excessive numbers in title
    numbers = re.findall(r'\d+', title)
    if len(numbers) >= 2:  # Multiple numbers suggests a list
        return True
    
    # Check for library guide URLs (.edu sites with /guides/, /research/, etc)
    library_guide_patterns = [
        r'/guides?/',
        r'research.*guide',
        r'libguides',
        r'library.*guide',
        r'subject.*guide',
    ]
    for pattern in library_guide_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    
    return False


def scrape_and_analyze(urls: List[str], theme: dict) -> List[LinkCandidate]:
    """Scrape content from URLs and analyze relevance."""
    scraper = WebScraper()
    theme_name = theme.get("name", "").lower()
    links_direction = theme.get("links", theme_name).lower()
    
    candidates = []
    listicle_count = 0
    failed_count = 0
    success_count = 0
    
    print(f"\nScraping {len(urls)} candidates...")
    
    for i, url in enumerate(urls, 1):
        print(f"\n  [{i}/{len(urls)}] {url}")
        
        candidate = LinkCandidate(url)
        
        # Scrape the page
        scraped = scraper.scrape_url(url)
        
        if scraped.error:
            print(f"    ✗ Failed: {scraped.error}")
            candidate.error = scraped.error
            failed_count += 1
            continue
        
        # Store scraped data
        candidate.title = scraped.title
        candidate.description = scraped.description
        candidate.content = scraped.content[:3000]  # Limit content
        candidate.concepts = scraped.concepts
        candidate.obscurity_score = scraped.obscurity_score
        
        # Reject listicles early
        if is_listicle_url(candidate.url, candidate.title):
            print(f"    ✗ Rejected (listicle/junk): {scraped.title[:60]}...")
            print(f"    🔍 Listicle patterns matched in: {url}")
            candidate.error = "Listicle/junk content detected"
            listicle_count += 1
            continue
        
        # Check .edu domains (early filter)
        if urlparse(candidate.url).netloc.endswith('.edu'):
            print(f"    ✗ Rejected (.edu domain): {scraped.title[:60]}...")
            candidate.error = ".edu domain filtered"
            continue
        
        print(f"    ✓ Scraped: {scraped.title[:60]}...")
        print(f"    Concepts: {', '.join(scraped.concepts[:5])}")
        print(f"    Obscurity: {scraped.obscurity_score:.2f}")
        success_count += 1
        
        candidates.append(candidate)
    
    print(f"\n📊 Scraping Summary:")
    print(f"  ✓ Successfully scraped: {success_count}")
    print(f"  ✗ Failed: {failed_count}")
    print(f"  ⏭ Filtered as listicles: {listicle_count}")
    
    return candidates


def calculate_relevance_score(candidate: LinkCandidate, theme: dict) -> float:
    """Calculate how relevant the content is to the theme."""
    theme_name = theme.get("name", "").lower()
    links_direction = theme.get("links", theme_name).lower()
    theme_words = set(theme_name.split() + links_direction.split())
    
    score = 0.0
    content_lower = candidate.content.lower()
    title_lower = candidate.title.lower()
    
    # Check for theme word matches in title (high weight)
    title_matches = sum(1 for word in theme_words if word in title_lower)
    score += min(title_matches * 0.25, 0.5)
    
    # Check for theme word matches in content
    content_matches = sum(1 for word in theme_words if word in content_lower)
    score += min(content_matches * 0.05, 0.3)
    
    # Check concept relevance
    concept_matches = 0
    for concept in candidate.concepts:
        concept_lower = concept.lower()
        if any(word in concept_lower for word in theme_words):
            concept_matches += 1
    score += min(concept_matches * 0.1, 0.2)
    
    return min(score, 1.0)


def verify_relevance_with_llm(candidate: LinkCandidate, theme: dict) -> float:
    """Use LLM to verify content relevance to theme."""
    if not API_KEY:
        return calculate_relevance_score(candidate, theme)
    
    theme_name = theme.get("name", "")
    links_direction = theme.get("links", theme_name)
    
    prompt = f"""Rate the relevance of this web page to the topic: "{links_direction}"

Title: {candidate.title}
Description: {candidate.description}
Content excerpt: {candidate.content[:1000]}

On a scale of 0.0 to 1.0, how relevant is this page to the topic?
- 1.0 = Highly relevant, directly about the topic
- 0.5 = Somewhat related
- 0.0 = Not related at all

Respond with ONLY a number between 0.0 and 1.0."""

    try:
        client = OpenAI(api_key=API_KEY, base_url=API_BASE)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You rate content relevance. Respond with only a number."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=10
        )
        
        content = response.choices[0].message.content.strip()
        
        # Extract number
        match = re.search(r'(\d+\.?\d*)', content)
        if match:
            score = float(match.group(1))
            return min(max(score, 0.0), 1.0)
        
    except Exception as e:
        print(f"    LLM relevance check failed: {e}")
    
    # Fallback to keyword matching
    return calculate_relevance_score(candidate, theme)


def score_candidates(candidates: List[LinkCandidate], theme: dict) -> List[LinkCandidate]:
    """Score all candidates for relevance and obscurity."""
    print(f"\nScoring {len(candidates)} candidates...")
    
    for i, candidate in enumerate(candidates, 1):
        print(f"\n  [{i}/{len(candidates)}] {candidate.url}")
        
        # Calculate relevance
        relevance = verify_relevance_with_llm(candidate, theme)
        candidate.relevance_score = relevance
        
        # Combined score: relevance * 0.7 + obscurity * 0.3
        candidate.final_score = (relevance * 0.7) + (candidate.obscurity_score * 0.3)
        
        print(f"    Relevance: {relevance:.2f}")
        print(f"    Obscurity: {candidate.obscurity_score:.2f}")
        print(f"    Final: {candidate.final_score:.2f}")
    
    return candidates


def calculate_content_similarity(candidate1: LinkCandidate, candidate2: LinkCandidate) -> float:
    """Calculate similarity between two candidates (0-1, higher = more similar)."""
    # Extract keywords from titles
    def get_keywords(text):
        text = text.lower()
        # Remove common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
                     'that', 'were', 'was', 'are', 'is', 'be', 'been', 'being', 'have', 'has', 'had',
                     'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
                     'can', 'this', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'}
        words = re.findall(r'\b[a-z]+\b', text)
        return set(w for w in words if w not in stopwords and len(w) > 3)
    
    title1_keywords = get_keywords(candidate1.title)
    title2_keywords = get_keywords(candidate2.title)
    
    # Title similarity (Jaccard index)
    if title1_keywords and title2_keywords:
        intersection = len(title1_keywords & title2_keywords)
        union = len(title1_keywords | title2_keywords)
        title_sim = intersection / union if union > 0 else 0
    else:
        title_sim = 0
    
    # Concept overlap
    concepts1 = set(c.lower() for c in candidate1.concepts[:5])
    concepts2 = set(c.lower() for c in candidate2.concepts[:5])
    if concepts1 and concepts2:
        concept_overlap = len(concepts1 & concepts2) / min(len(concepts1), len(concepts2))
    else:
        concept_overlap = 0
    
    # Combined similarity (weighted)
    return (title_sim * 0.7) + (concept_overlap * 0.3)


def select_best_links(candidates: List[LinkCandidate], count: int = 7) -> List[LinkCandidate]:
    """Select the best links based on final score with diversity checks."""
    # Filter out candidates with errors, low scores, or .edu domains
    print(f"\n🔍 Filtering {len(candidates)} candidates:")
    
    # Track filtering reasons
    filter_stats = {
        "errors": 0,
        "low_relevance": 0,
        "low_obscurity": 0,
        "edu_domain": 0,
        "boilerplate": 0,
        "passed": 0
    }
    
    valid = []
    for c in candidates:
        if c.error:
            filter_stats["errors"] += 1
            print(f"  ✗ {c.url[:60]}... - ERROR: {c.error}")
            continue
        
        if urlparse(c.url).netloc.endswith('.edu'):
            filter_stats["edu_domain"] += 1
            print(f"  ✗ {c.url[:60]}... - .edu domain filtered")
            continue
            
        if c.relevance_score < MIN_RELEVANCE_SCORE:
            filter_stats["low_relevance"] += 1
            print(f"  ✗ {c.url[:60]}... - Low relevance: {c.relevance_score:.2f} < {MIN_RELEVANCE_SCORE}")
            continue
            
        if c.obscurity_score < MIN_OBSCURITY_SCORE:
            filter_stats["low_obscurity"] += 1
            print(f"  ✗ {c.url[:60]}... - Low obscurity: {c.obscurity_score:.2f} < {MIN_OBSCURITY_SCORE}")
            continue

        if looks_like_boilerplate(c):
            filter_stats["boilerplate"] += 1
            print(f"  ✗ {c.url[:60]}... - Looks like boilerplate (contact/privacy/etc.)")
            continue
        
        filter_stats["passed"] += 1
        valid.append(c)
    
    print(f"\n📊 Filtering Summary:")
    print(f"  ✓ Passed all filters: {filter_stats['passed']}")
    print(f"  ✗ Errors: {filter_stats['errors']}")
    print(f"  ✗ Low relevance (<{MIN_RELEVANCE_SCORE}): {filter_stats['low_relevance']}")
    print(f"  ✗ Low obscurity (<{MIN_OBSCURITY_SCORE}): {filter_stats['low_obscurity']}")
    print(f"  ✗ .edu domains: {filter_stats['edu_domain']}")
    print(f"  ✗ Boilerplate/contact pages: {filter_stats['boilerplate']}")
    
    fallback_mode = False
    if len(valid) < MINIMUM_SELECTED_LINKS:
        print(f"\n⚠️  Only {len(valid)} candidates passed strict filters; enabling fallback thresholds")
        fallback_mode = True
        for c in candidates:
            if c in valid or c.error or urlparse(c.url).netloc.endswith('.edu'):
                continue
            if looks_like_boilerplate(c):
                continue
            if c.relevance_score >= MIN_RELEVANCE_FALLBACK and c.obscurity_score >= MIN_OBSCURITY_FALLBACK:
                print(f"  ➕ Fallback candidate: {c.url[:60]}... (rel {c.relevance_score:.2f}, obs {c.obscurity_score:.2f})")
                valid.append(c)
            if len(valid) >= MINIMUM_SELECTED_LINKS:
                break

    if not valid:
        print("\n❌ No candidates passed filtering!")
        return []
    
    # Sort by final score
    sorted_candidates = sorted(valid, key=lambda x: x.final_score, reverse=True)
    
    # Select top N with diversity checks (domain + content)
    selected = []
    domains_used = []
    skipped_domain = 0
    skipped_similar = 0
    
    for candidate in sorted_candidates:
        if len(selected) >= count:
            break
        
        domain = urlparse(candidate.url).netloc
        
        # Skip if domain already used (max 3 links per domain)
        if domains_used.count(domain) >= 3:
            print(f"  ⏭ Skipping (domain limit reached): {candidate.title[:50]}...")
            skipped_domain += 1
            continue
        
        # Check content similarity with already selected links
        is_duplicate = False
        for existing in selected:
            similarity = calculate_content_similarity(candidate, existing)
            if similarity > 0.5:  # Skip if >50% similar
                print(f"  ⏭ Skipping (similarity {similarity:.0%} to '{existing.title[:40]}...'): {candidate.title[:40]}...")
                skipped_similar += 1
                is_duplicate = True
                break
        
        if is_duplicate:
            continue
        
        selected.append(candidate)
        domains_used.append(domain)
        print(f"  ✓ Selected: {candidate.title[:50]}... (score: {candidate.final_score:.2f})")
    
    print(f"\n📊 Selection Summary:")
    print(f"  ✓ Selected: {len(selected)}")
    print(f"  ⏭ Skipped (domain limit): {skipped_domain}")
    print(f"  ⏭ Skipped (similar content): {skipped_similar}")
    
    return selected


def _extract_summary_text(candidate: LinkCandidate) -> str:
    """Build cleaner summaries, preferring descriptions and sentence boundaries."""
    if candidate.description and len(candidate.description.strip()) >= 40:
        base = candidate.description.strip()
    else:
        content = candidate.content.replace('\n', ' ').strip()
        sentences = re.split(r'(?<=[.!?])\s+', content)
        base = ' '.join(sentences[:2]).strip()
    if not base:
        base = "No summary available yet—worth exploring directly."
    if len(base) > 320:
        base = base[:317].rstrip() + "..."
    return base


def _generate_tags(candidate: LinkCandidate) -> List[str]:
    """Create short tags using obscurity score and top concepts."""
    tags = [f"obs:{candidate.obscurity_score:.2f}"]
    for concept in candidate.concepts[:3]:
        slug = re.sub(r'[^a-z0-9]+', '-', concept.lower()).strip('-')
        if slug and slug not in tags:
            tags.append(slug[:24])
    return tags


def generate_summary(candidate: LinkCandidate, theme: dict) -> Tuple[str, str, List[str]]:
    """Generate title, cleaned summary, and tags for a link."""
    title = candidate.title.strip() or candidate.url
    if len(title) > 120:
        title = title[:117] + "..."
    summary = _extract_summary_text(candidate)
    tags = _generate_tags(candidate)
    return title, summary, tags


def save_links(links: List[LinkCandidate], theme: dict) -> Path:
    """Save the selected links as a markdown file."""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    theme_name = theme.get("name", "unknown")
    
    # Ensure posts directory exists
    posts_dir = Path("docs/links/posts")
    posts_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename
    filename = f"{date_str}-daily-links.md"
    filepath = posts_dir / filename
    
    # Build markdown content
    links_content = ""
    for i, link in enumerate(links, 1):
        title, summary, tags = generate_summary(link, theme)
        url = link.url
        tag_line = ', '.join(f"`{tag}`" for tag in tags) if tags else "``"
        
        links_content += f"""
## {i}. {title}

{summary}

Tags: {tag_line}

<a href="{url}" target="_blank" rel="noopener" class="visit-link">Visit Link →</a>

---
"""
    
    frontmatter = f"""---
date: {today}
title: "Obscure Links - {today.strftime('%B %d, %Y')}"
description: "Today's curated obscure links: {theme_name}"
author: "Obscure Bit"
theme: "{theme_name}"
---

"""
    
    content = f"""{frontmatter}
# Obscure Links - {today.strftime('%B %d, %Y')}

**Theme: {theme_name.title()}**

Today's curated discoveries from the hidden corners of the web.

{links_content}

<button class="share-btn" data-url="{{% raw %}}{{{{ page.canonical_url }}}}{{% endraw %}}" data-title="Obscure Links - {date_str}">
  Share today's links
</button>
"""
    
    filepath.write_text(content)
    print(f"\n✓ Saved {len(links)} links to: {filepath}")
    return filepath


def main():
    """Main entry point for link generation."""
    args = parse_args()
    theme_override = load_theme_override(args.theme_json)
    theme = theme_override or get_daily_theme()
    theme_name = theme.get("name", "unknown")
    print(f"\nTheme: {theme_name}")
    print(f"Direction: {theme.get('links', theme_name)}")

    print("=" * 70)
    print("Obscure Bit - Link Generation v2")
    print("=" * 70)
    
    if not API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Step 1: Get candidate URLs
    print("\n" + "=" * 70)
    print("STEP 1: Finding Candidate URLs")
    print("=" * 70)
    candidates_urls = get_candidate_urls(theme)
    
    if not candidates_urls:
        print("Error: No candidate URLs found")
        sys.exit(1)
    
    # Step 2: Scrape and analyze
    print("\n" + "=" * 70)
    print("STEP 2: Scraping Content")
    print("=" * 70)
    candidates = scrape_and_analyze(candidates_urls, theme)
    
    valid_candidates = [c for c in candidates if c.error is None]
    print(f"\nSuccessfully scraped {len(valid_candidates)}/{len(candidates)} URLs")
    
    if len(valid_candidates) < 3:
        print("Error: Too few valid candidates")
        sys.exit(1)
    
    # Step 3: Score candidates
    print("\n" + "=" * 70)
    print("STEP 3: Scoring Relevance & Obscurity")
    print("=" * 70)
    scored = score_candidates(valid_candidates, theme)
    
    # Step 4: Select best
    print("\n" + "=" * 70)
    print("STEP 4: Selecting Best Links")
    print("=" * 70)
    selected = select_best_links(scored, count=7)
    
    if not selected:
        print("Error: No links passed scoring thresholds")
        sys.exit(1)
    
    print(f"\n✓ Selected {len(selected)} links")
    
    # Step 5: Save
    print("\n" + "=" * 70)
    print("STEP 5: Saving Results")
    print("=" * 70)
    filepath = save_links(selected, theme)
    
    print("\n" + "=" * 70)
    print("SUCCESS!")
    print("=" * 70)
    print(f"Generated {len(selected)} curated links")
    print(f"Saved to: {filepath}")
    
    return selected, theme


if __name__ == "__main__":
    main()
