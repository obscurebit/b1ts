# Obscure Bit System Design

## Overview

Obscure Bit is an automated content generation system that creates and publishes daily tech stories, links, and newsletter editions. A single orchestrator (`run_daily.py`) synchronizes theme selection and triggers the story, link, and landing generators. The system runs on GitHub Actions for content generation and publishes to GitHub Pages. Substack publishing requires local execution due to Cloudflare restrictions.

## Architecture

```mermaid
graph TB
    subgraph "GitHub Actions (Daily 6AM UTC)"
        A[run_daily.py (story+links+landing)] --> B[Update Landing Pages]
        B --> C[Commit & Push]
    end
    
    subgraph "Local Machine (Manual)"
        D[Publish to Substack]
    end
    
    subgraph "Content Sources"
        E[OpenAI API] --> A
        F[Prompts & Seeds] --> A
        W[LLM Strategy + Web Search APIs] --> A
        SM[Style Modifiers<br/>SHA-256 date seed] --> A
    end
    
    subgraph "Outputs"
        G[GitHub Pages Site]
        H[Substack Drafts]
        I[Markdown History]
    end
    
    A --> G
    A --> I
    D --> H
    
    subgraph "Manual Actions"
        J[Review Draft] --> K[Publish to Substack]
        L[Edit Posts] --> M[Regenerate Content]
    end
    
    H --> J
    G --> L
    M --> A
```

## Data Flow

```mermaid
flowchart LR
    subgraph "Input"
        A1[OpenAI API]
        A2[Story Prompts]
        A3[Link Seeds]
        SM[style_modifiers.yaml]
    end
    
    subgraph "Generation"
        B1[generate_story.py]
        B2[generate_links.py]
        B3[update_landing.py]
        WS[web_scraper.py]
    end
    
    WS --> B2
    
    subgraph "Storage"
        C1["docs/bits/posts/<br/>(frontmatter: theme, genre)"]
        C2[docs/links/posts/]
        C3[docs/editions/posts/]
        C4[docs/substack/]
    end
    
    subgraph "Publishing"
        D1[GitHub Pages]
        D2[Substack API]
    end
    
    A1 --> B1
    A2 --> B1
    SM --> B1
    W --> B2
    A3 --> B2
    WS --> B2
    B1 --> C1
    B2 --> C2
    B3 --> C3
    B3 --> C4
    C1 --> D1
    C2 --> D1
    C3 --> D1
    C4 --> D2
```

## Style Modifiers System

Each story is shaped by randomized constraints drawn from `prompts/style_modifiers.yaml`. This ensures variety even when themes repeat on their 18-day rotation.

```mermaid
flowchart TD
    DATE["Date (YYYY-MM-DD)"] --> HASH["SHA-256 hash → seed"]
    HASH --> RNG["Seeded RNG"]
    
    subgraph "Style Dimensions (9)"
        POV[pov · 15 options]
        TONE[tone · 15 options]
        ERA[era · 15 options]
        SET[setting · 16 options]
        STR[structure · 14 options]
        CON[conflict · 14 options]
        OPEN[opening · 14 options]
        GEN[genre · 15 options]
        WILD[wildcard · 12 options]
    end
    
    RNG --> POV & TONE & ERA & SET & STR & CON & OPEN & GEN & WILD
    
    subgraph "Banned Words"
        BAN["12 word sets · 7 words each"]
    end
    
    RNG --> BAN
    
    POV & TONE & ERA & SET & STR & CON & OPEN & GEN & WILD --> PROMPT["Story prompt<br/>with TODAY'S CONSTRAINTS"]
    BAN --> PROMPT
    GEN --> FM["Frontmatter: genre field"]
    FM --> CARDS["Landing page + archive genre tags"]
```

### Properties
- **Deterministic**: Same date → same modifiers (reproducible backfills)
- **Combinatorial**: ~15^9 × 12 ≈ 460 billion unique combinations
- **Anti-repetition**: Banned word sets rotate to prevent stylistic staleness
- **Genre propagation**: Genre flows from modifier → frontmatter → HTML cards via `update_landing.py`

## Link Generation Architecture (v3.1 - Registry + Quality Gates)

The link generation system uses a multi-stage pipeline with LLM-driven research strategy, active web search, and a persistent URL registry for cross-day deduplication:

```mermaid
flowchart LR
    subgraph "Stage 1: LLM Research Strategy"
        RS1[Load research_strategy_system.md]
        RS2[LLM generates domain ideas]
        RS3[LLM generates search queries]
        RS4[Parse structured output]
    end
    
    subgraph "Stage 2: Discovery"
        D1[Execute LLM search queries]
        D2[Extended sources (42 APIs)]
        D3[SerpAPI / ContextualWeb]
        D4[Marginalia (primary fallback)]
    end
    
    subgraph "Stage 2b: Registry Filter"
        REG[link_registry.py]
        REG2[SHA-256 URL hash lookup]
        REG3[Reject previously-published URLs]
    end
    
    subgraph "Stage 3: Scraping"
        S1[Fetch Content]
        S2[Extract Concepts]
        S3[Score Obscurity]
    end
    
    subgraph "Stage 4: Verification"
        V1[LLM Relevance Check]
        V2[Keyword Fallback]
    end
    
    subgraph "Stage 5: Selection"
        SEL[Score: 70% relevance + 30% obscurity]
        QG[Listicle + junk domain filter]
        DIV[Content similarity filter]
        DOM[Domain Diversity max 3/domain]
        EDU[Filter .edu + disallowed domains]
    end
    
    RS1 --> RS2
    RS2 --> RS3
    RS3 --> RS4
    RS4 --> D1
    D1 --> REG
    D2 --> REG
    D3 --> REG
    D4 --> REG
    REG --> REG2
    REG2 --> REG3
    REG3 --> S1
    S1 --> S2
    S2 --> S3
    S3 --> V1
    V1 --> SEL
    V2 --> SEL
    SEL --> QG
    QG --> DIV
    DIV --> DOM
    DOM --> EDU
    EDU --> OUT[Top 7 Links]
    OUT --> REG4[Register in registry]
```

### Research Strategy System

The new approach asks the LLM to act as a **research strategist** rather than directly suggesting URLs:

1. **Domain Ideas**: LLM suggests 5 creative domain categories (niche history blogs, museum collections, research departments, etc.)
2. **Search Queries**: LLM generates 5 specific, SEO-avoiding queries using technical terms and dates
3. **Query Execution**: System executes queries via DuckDuckGo to discover actual URLs
4. **Direct URLs**: Any URLs the LLM knows with confidence are also included

This approach surfaces obscure content by:
- Avoiding broad keywords that attract clickbait
- Using technical/academic vocabulary
- Searching across diverse domains
- Filtering listicles and SEO-optimized content early

### Resilient Search Stack

To survive DuckDuckGo throttling while still surfacing at least seven high-quality links, the discovery stage fans out across multiple providers:

1. **DuckDuckGo Lite** – limited to **1 query per run** to avoid 202 throttle storms in CI. Disables after the first failure. Used only for the broadest theme query; all other searches route through alternative providers.
2. **SerpAPI (Google)** – triggered automatically when `SERPAPI_KEY` is present; supplies clean organic URLs for broad theme queries. Now the primary search engine.
3. **ContextualWeb Search** – optional RapidAPI fallback for additional coverage.
4. **Marginalia.nu** – indie search engine that handles all `site:` domain queries and serves as the automatic fallback whenever DDG budget is exhausted or throttled.
5. **Curated fallback queries** – `run_fallback_searches()` hits dependable domains (Library of Congress, Smithsonian, Wilson Center, etc.) plus generic "oral history / archives / declassified" searches, ensuring variety even when all other sources are sparse.
6. **Backup booster queries** – if the deduplicated pool has <25 URLs, broad "hidden history" prompts run through Marginalia.

### URL Registry (Cross-Day Deduplication)

A persistent SHA-256 hash registry (`cache/link_registry.json`) prevents the same URL from ever being published twice:

1. **Normalize** – lowercase domain, strip `www.`, remove tracking params (`utm_*`, `fbclid`, etc.), sort query params, strip trailing slashes
2. **Hash** – SHA-256 of the normalized URL → deterministic key
3. **Filter** – before scoring, every candidate URL is checked against the registry; known URLs are rejected
4. **Register** – after saving, all selected URLs are added to the registry with date, theme, title, and domain metadata
5. **Domain frequency** – the registry tracks per-domain counts across all days, enabling future global diversity caps

The registry was backfilled from all existing posts via `scripts/backfill_registry.py`.

### Quality Gates

Multiple layers prevent low-quality content from reaching publication:

- **Disallowed domains**: Wikipedia, Archive.org, GitHub, `.edu` domains, plus a blocklist of junk/listicle sites (Listverse, BuzzFeed, Ranker, etc.)
- **Listicle filter**: Catches numbered titles ("5 Cold War Close Calls"), clickbait patterns, game guides, and tip pages
- **Domain filtering at every stage**: `search_extended_sources()` and `search_academic_sources()` now filter disallowed domains before returning URLs
- **Fallback floor**: Emergency fallback thresholds bottom out at (0.15, 0.15) — no more zero-threshold "accept anything" mode
- **Boilerplate detection**: Contact pages, privacy policies, and thin content are filtered

Downstream safeguards guarantee at least three published links by temporarily relaxing relevance/obscurity thresholds (floor: 0.15/0.15) when the strict pass yields too few candidates.

## Action Flows

### 1. Daily Content Generation (Automated)

```mermaid
sequenceDiagram
    participant GA as GitHub Actions
    participant AI as OpenAI API
    participant GH as GitHub Repo
    participant SS as Substack API
    
    GA->>GA: Select theme (rotation or override)
    GA->>GA: Select style modifiers (SHA-256 date seed)
    GA->>AI: Generate story (theme + modifiers)
    AI-->>GA: Story content + genre
    GA->>AI: Generate links (theme direction)
    AI-->>GA: Links content
    
    GA->>GH: Save story to docs/bits/posts/ (genre in frontmatter)
    GA->>GH: Save links to docs/links/posts/
    GA->>GH: Create edition snapshot (genre in frontmatter)
    GA->>GH: Update landing page + archives (genre tags on cards)
    
    GA->>GH: Commit changes
    GA->>GH: Push to main
    
    Note over GA: Content ready for local Substack publish
```

### 1b. Backfill Generation (Manual)

All scripts accept `--date YYYY-MM-DD` to generate content for past dates. The date controls theme selection, style modifier seed, and output filenames.

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant RD as run_daily.py
    participant GS as generate_story.py
    participant GL as generate_links.py
    
    Dev->>RD: --date 2026-02-10 --skip-landing
    RD->>RD: select_theme("2026-02-10")
    RD->>GL: --date 2026-02-10 --theme-json {...}
    GL->>GL: save_links(target_date=Feb 10)
    RD->>GS: --date 2026-02-10 --theme-json {...}
    GS->>GS: select_style_modifiers(seed=SHA256("2026-02-10"))
    GS->>GS: save_story(target_date=Feb 10)
    
    Dev->>Dev: python scripts/update_landing.py
    Note over Dev: Rebuild archives to include backfilled content
```

### 2. Local Substack Publishing (Manual)

**Note:** Substack uses Cloudflare protection that blocks GitHub Actions datacenter IPs. Publishing must be done locally.

```mermaid
sequenceDiagram
    participant User as Local Machine
    participant PW as Playwright Browser
    participant SS as Substack
    
    User->>PW: python scripts/substack_playwright.py --edition N --draft
    PW->>SS: Open editor (bypasses Cloudflare)
    PW->>SS: Fill title, subtitle, content
    SS->>SS: Auto-save draft
    
    User->>SS: Review draft in browser
    User->>SS: Click Publish
    
    Note over User: Or use --publish flag to publish directly
```

#### Local Setup
```bash
# One-time: Install Playwright and login
pip3 install playwright
python3 -m playwright install chromium
python3 scripts/substack_playwright.py --login

# Daily: Publish edition
python3 scripts/substack_playwright.py --edition 3 --draft
```

### 3. Content Update Flow

```mermaid
sequenceDiagram
    participant User as User
    participant GH as GitHub Repo
    participant GA as GitHub Actions
    
    User->>GH: Edit post in docs/
    User->>GH: git push
    
    GA->>GH: Detect changes
    GA->>GH: Regenerate landing pages
    GA->>GH: Update navigation
    GA->>GH: Commit updates
    
    Note over GA: Substack not affected (prevents duplicates)
```

## File Structure

```
b1ts/
├── .github/workflows/
│   └── generate-content.yml    # Daily automation
├── docs/
│   ├── bits/posts/             # Daily stories
│   ├── links/posts/            # Daily links
│   ├── editions.md             # Edition archive
│   ├── substack/               # Newsletter drafts & history
│   │   ├── YYYY-MM-DD-edition-XXX.md
│   │   └── edition-XXX-published.txt
│   └── stylesheets/
├── scripts/
│   ├── run_daily.py            # Theme orchestrator (story + links + landing)
│   ├── generate_story.py       # AI story generation
│   ├── generate_links.py       # Enhanced links with LLM research + multi-source search (v3.1)
│   ├── link_registry.py        # Persistent SHA-256 URL registry for cross-day dedup
│   ├── backfill_registry.py    # One-time script to seed registry from existing posts
│   ├── generate_links_old.py   # Legacy links generation (archived)
│   ├── web_scraper.py          # Content extraction & analysis
│   ├── update_landing.py       # Site updates (parses genre → HTML tags)
│   ├── publish_substack.py     # Substack API publishing
│   ├── substack_playwright.py  # Cookie extraction helper
│   └── test_web_access.py      # Web access diagnostics
├── prompts/
│   ├── story_system.md         # Story generation prompts
│   ├── links_system.md         # Links content generation prompts
│   ├── research_strategy_system.md  # LLM research strategy prompts
│   ├── themes.yaml             # Unified themes for stories + links
│   └── style_modifiers.yaml    # Randomized story constraint pools (9 dimensions)
└── cache/
    ├── link_registry.json      # Persistent URL hash registry (cross-day dedup)
    └── web_content/            # Cached scraped content
```

## Environment Variables

### GitHub Secrets
```yaml
OPENAI_API_KEY:          # OpenAI API access
OPENAI_API_BASE:         # API endpoint (NVIDIA)
OPENAI_MODEL:            # Model name
SERPAPI_KEY:             # Optional SerpAPI key for resilient search
CONTEXTUALWEB_API_KEY:   # Optional RapidAPI key (ContextualWeb backup)
# Note: Substack secrets removed - Cloudflare blocks CI
```

### Local Development
```bash
export OPENAI_API_KEY="..."
export OPENAI_API_BASE="https://integrate.api.nvidia.com/v1"
export OPENAI_MODEL="nvidia/llama-3.3-nemotron-super-49b-v1.5"
export SERPAPI_KEY="optional-serpapi-key"
export CONTEXTUALWEB_API_KEY="optional-rapidapi-key"
export SUBSTACK_PUBLICATION_URL="https://obscurebit.substack.com"
export SUBSTACK_COOKIES_PATH="$HOME/.substack_cookies.json"
```

## Publishing States

```mermaid
stateDiagram-v2
    [*] --> Generated: Daily workflow
    Generated --> Draft: Create draft
    Draft --> Published: Manual publish
    Draft --> Edited: Edit content
    Edited --> Draft: Regenerate
    Published --> [*]: Complete
    
    note right of Published
        Marker file created:
        docs/substack/edition-XXX-published.txt
        Prevents duplicate publishing
    end note
```

## Error Handling

### OpenAI API Failures
- Retry mechanism with exponential backoff
- Fallback to cached content if available
- Continue with other content types

### Substack Failures
- Cloudflare blocks GitHub Actions IPs (use local publishing)
- Playwright browser automation bypasses Cloudflare locally
- Browser state saved in ~/.playwright_state.json
- Draft creation is non-destructive
- Duplicate prevention protects against retries

### GitHub Actions Failures
- Workflow continues on partial failures
- Content generation independent from publishing
- Manual recovery possible

## Scaling Considerations

### Content Volume
- Daily editions: ~365 posts/year
- Storage: Minimal (markdown files)
- API calls: ~4-6 per day (story generation, link research strategy, link scoring, link summaries)

### Performance
- Generation time: ~30 seconds
- Site rebuild: ~2 minutes
- Substack draft: ~10 seconds

### Cost Management
- OpenAI tokens: ~5K per day
- GitHub Actions: Free tier sufficient
- Substack: Free tier

## Future Enhancements

1. **Scheduled Publishing**: Auto-publish drafts at specific times
2. **Content Caching**: Reduce API calls for unchanged content
3. **Multi-platform**: Add Twitter, LinkedIn integration
4. **Analytics**: Track engagement and optimize content
5. **A/B Testing**: Test different content formats

## Security Considerations

- All secrets stored in GitHub Secrets
- No credentials in code
- Cookie-based auth for Substack
- Read-only file permissions for content

## Monitoring

- GitHub Actions dashboard for workflow status
- Draft review in Substack dashboard
- Site health via GitHub Pages status
- Error notifications via GitHub issues
- Mixpanel telemetry embedded in the site head records anonymous story/link views (autocapture + manual `Story Viewed` / `Links Viewed` events), giving real-time engagement while keeping everything anonymous by default.
