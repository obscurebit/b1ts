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
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus, urlparse
import random

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

# Paths
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "links_system.md"
THEMES_FILE = PROMPTS_DIR / "themes.yaml"
CACHE_DIR = Path("cache/link_generation")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Search configuration
SEARCH_TIMEOUT = 15
MAX_CANDIDATES = 30
MIN_RELEVANCE_SCORE = 0.6
MIN_OBSCURITY_SCORE = 0.3


def load_system_prompt() -> str:
    """Load the system prompt from external file."""
    if not SYSTEM_PROMPT_FILE.exists():
        return "You are a helpful assistant that finds obscure and interesting web links."
    return SYSTEM_PROMPT_FILE.read_text().strip()


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
    """Search DuckDuckGo for URLs matching the query."""
    urls = []
    try:
        # Try DuckDuckGo Lite (more reliable HTML)
        search_url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=SEARCH_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # DuckDuckGo lite uses .result-link or direct links
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            # Extract actual URL from DDG redirect
            if href.startswith('http'):
                # Skip DDG's own URLs
                if 'duckduckgo.com' not in href:
                    urls.append(href)
            elif '/l/?' in href:
                # Extract from DDG redirect format: /l/?uddg=http...
                uddg_match = re.search(r'uddg=([^&]+)', href)
                if uddg_match:
                    from urllib.parse import unquote
                    actual_url = unquote(uddg_match.group(1))
                    if actual_url.startswith('http'):
                        urls.append(actual_url)
                
        # Remove duplicates and clean
        seen = set()
        clean_urls = []
        for url in urls:
            # Skip search engines, social media, etc
            skip_domains = ['duckduckgo.com', 'google.com', 'bing.com', 'facebook.com', 
                          'twitter.com', 'instagram.com', 'youtube.com', 'reddit.com']
            domain = urlparse(url).netloc.lower()
            if any(skip in domain for skip in skip_domains):
                continue
            if url not in seen:
                seen.add(url)
                clean_urls.append(url)
                
        print(f"  Found {len(clean_urls)} URLs from DuckDuckGo")
        return clean_urls[:max_results]
        
    except Exception as e:
        print(f"  DuckDuckGo search failed: {e}")
        return []


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


def get_candidate_urls(theme: dict) -> List[str]:
    """Generate candidate URLs from multiple search sources."""
    theme_name = theme.get("name", "")
    links_direction = theme.get("links", theme_name)
    
    print(f"\nSearching for: {links_direction}")
    
    all_urls = []
    
    # 1. DuckDuckGo search with different queries
    queries = [
        f"{links_direction} obscure interesting",
        f"{links_direction} hidden gems",
        f"{theme_name} {links_direction} research",
        f"site:.edu {links_direction}",
        f"site:.gov {links_direction}",
    ]
    
    for query in queries[:3]:  # Limit to 3 queries to avoid rate limits
        print(f"\n  Query: {query}")
        urls = search_duckduckgo(query, max_results=8)
        all_urls.extend(urls)
    
    # 2. Academic/archival sources
    print(f"\n  Searching academic sources...")
    academic_urls = search_academic_sources(theme_name, links_direction)
    all_urls.extend(academic_urls)
    
    # 3. Get LLM-suggested URLs for variety
    print(f"\n  Getting LLM suggestions...")
    llm_urls = get_llm_candidate_urls(theme)
    all_urls.extend(llm_urls)
    
    # Deduplicate and limit
    seen = set()
    unique_urls = []
    for url in all_urls:
        if url not in seen and len(unique_urls) < MAX_CANDIDATES:
            seen.add(url)
            unique_urls.append(url)
    
    print(f"\nTotal unique candidates: {len(unique_urls)}")
    return unique_urls


def get_llm_candidate_urls(theme: dict) -> List[str]:
    """Ask LLM for URL suggestions based on theme."""
    if not API_KEY:
        return []
    
    theme_name = theme.get("name", "")
    links_direction = theme.get("links", theme_name)
    
    prompt = f"""Suggest 5 real, verifiable URLs about: {links_direction}

These should be actual web pages that exist and are related to the topic.
Prefer .edu, .gov, archive.org, Wikipedia, or well-known sites.

Respond with ONLY the URLs, one per line, starting with http:// or https://
Example format:
https://example.com/page1
https://archive.org/details/item2"""

    try:
        client = OpenAI(api_key=API_KEY, base_url=API_BASE)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You suggest real, working URLs from your training data. Only output valid URLs."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        content = response.choices[0].message.content
        
        # Extract URLs with validation
        urls = []
        for match in re.finditer(r'https?://[^\s<>"\'\)\]\}]+', content):
            url = match.group(0)
            # Basic validation
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc and '.' in parsed.netloc:
                # Skip if it's just a domain placeholder
                if len(parsed.netloc) > 3:
                    urls.append(url)
        
        print(f"    LLM suggested {len(urls)} valid URLs")
        return urls[:5]
        
    except Exception as e:
        print(f"    LLM suggestion failed: {e}")
        return []


def scrape_and_analyze(urls: List[str], theme: dict) -> List[LinkCandidate]:
    """Scrape content from URLs and analyze relevance."""
    scraper = WebScraper()
    theme_name = theme.get("name", "").lower()
    links_direction = theme.get("links", theme_name).lower()
    
    candidates = []
    
    print(f"\nScraping {len(urls)} candidates...")
    
    for i, url in enumerate(urls, 1):
        print(f"\n  [{i}/{len(urls)}] {url}")
        
        candidate = LinkCandidate(url)
        
        # Scrape the page
        scraped = scraper.scrape_url(url)
        
        if scraped.error:
            print(f"    ✗ Failed: {scraped.error}")
            candidate.error = scraped.error
            continue
        
        # Store scraped data
        candidate.title = scraped.title
        candidate.description = scraped.description
        candidate.content = scraped.content[:3000]  # Limit content
        candidate.concepts = scraped.concepts
        candidate.obscurity_score = scraped.obscurity_score
        
        print(f"    ✓ Scraped: {scraped.title[:60]}...")
        print(f"    Concepts: {', '.join(scraped.concepts[:5])}")
        print(f"    Obscurity: {scraped.obscurity_score:.2f}")
        
        candidates.append(candidate)
    
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
    # Filter out candidates with errors or low scores
    valid = [
        c for c in candidates 
        if c.error is None 
        and c.relevance_score >= MIN_RELEVANCE_SCORE
        and c.obscurity_score >= MIN_OBSCURITY_SCORE
    ]
    
    print(f"\n{len(valid)} candidates passed minimum thresholds")
    print(f"  Min relevance: {MIN_RELEVANCE_SCORE}")
    print(f"  Min obscurity: {MIN_OBSCURITY_SCORE}")
    
    # Sort by final score
    sorted_candidates = sorted(valid, key=lambda x: x.final_score, reverse=True)
    
    # Select top N with diversity checks (domain + content)
    selected = []
    
    for candidate in sorted_candidates:
        if len(selected) >= count:
            break
        
        domain = urlparse(candidate.url).netloc
        
        # Check domain diversity (max 2 links from same domain)
        domain_count = sum(1 for s in selected if urlparse(s.url).netloc == domain)
        if domain_count >= 2:
            continue
        
        # Check content similarity with already selected links
        is_duplicate = False
        for existing in selected:
            similarity = calculate_content_similarity(candidate, existing)
            if similarity > 0.5:  # Lower threshold - skip if >50% similar
                print(f"  ⏭ Skipping (similarity {similarity:.0%} to '{existing.title[:40]}...'): {candidate.title[:40]}...")
                is_duplicate = True
                break
        
        if is_duplicate:
            continue
        
        selected.append(candidate)
        print(f"  ✓ Selected: {candidate.title[:50]}... (score: {candidate.final_score:.2f})")
    
    return selected


def generate_summary(candidate: LinkCandidate, theme: dict) -> Tuple[str, str]:
    """Generate title and summary for a link."""
    # Clean up title
    title = candidate.title
    if len(title) > 100:
        title = title[:97] + "..."
    
    # Use description if available, otherwise extract from content
    if candidate.description and len(candidate.description) > 20:
        summary = candidate.description
    else:
        summary = candidate.content[:200] + "..." if len(candidate.content) > 200 else candidate.content
    
    # Clean up summary
    summary = summary.replace('\n', ' ').strip()
    if len(summary) > 300:
        summary = summary[:297] + "..."
    
    # Generate "why obscure" text
    why = f"Obscurity score: {candidate.obscurity_score:.2f}. "
    if candidate.concepts:
        why += f"Key concepts: {', '.join(candidate.concepts[:3])}."
    
    return title, summary, why


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
        title, summary, why = generate_summary(link, theme)
        url = link.url
        
        links_content += f"""
## {i}. {title}

{summary}

*{why}*

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
    print("=" * 70)
    print("Obscure Bit - Link Generation v2")
    print("=" * 70)
    
    if not API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Get theme
    theme = get_daily_theme()
    theme_name = theme.get("name", "unknown")
    print(f"\nTheme: {theme_name}")
    print(f"Direction: {theme.get('links', theme_name)}")
    
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
