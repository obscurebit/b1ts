# Obscure Bit System Design

## Overview

Obscure Bit is an automated content generation system that creates and publishes daily tech stories, links, and newsletter editions. The system runs on GitHub Actions for content generation and publishes to GitHub Pages. Substack publishing requires local execution due to Cloudflare restrictions.

## Architecture

```mermaid
graph TB
    subgraph "GitHub Actions (Daily 6AM UTC)"
        A[Generate Content] --> B[Update Landing Pages]
        B --> C[Commit & Push]
    end
    
    subgraph "Local Machine (Manual)"
        D[Publish to Substack]
    end
    
    subgraph "Content Sources"
        E[OpenAI API] --> A
        F[Prompts & Seeds] --> A
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
    end
    
    subgraph "Generation"
        B1[generate_story.py]
        B2[generate_links.py]
        B3[update_landing.py]
    end
    
    subgraph "Storage"
        C1[docs/bits/posts/]
        C2[docs/links/posts/]
        C3[docs/editions.md]
        C4[docs/substack/]
    end
    
    subgraph "Publishing"
        D1[GitHub Pages]
        D2[Substack API]
    end
    
    A1 --> B1
    A2 --> B1
    A1 --> B2
    A3 --> B2
    B1 --> C1
    B2 --> C2
    B3 --> C3
    B3 --> C4
    C1 --> D1
    C2 --> D1
    C3 --> D1
    C4 --> D2
```

## Action Flows

### 1. Daily Content Generation (Automated)

```mermaid
sequenceDiagram
    participant GA as GitHub Actions
    participant AI as OpenAI API
    participant GH as GitHub Repo
    participant SS as Substack API
    
    GA->>AI: Generate story
    AI-->>GA: Story content
    GA->>AI: Generate links
    AI-->>GA: Links content
    
    GA->>GH: Save story to docs/bits/posts/
    GA->>GH: Save links to docs/links/posts/
    GA->>GH: Update editions.md
    GA->>GH: Update landing pages
    
    GA->>GH: Commit changes
    GA->>GH: Push to main
    
    Note over GA: Content ready for local Substack publish
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
│   ├── generate_story.py       # AI story generation
│   ├── generate_links.py       # AI links generation
│   ├── update_landing.py       # Site updates
│   └── publish_substack.py     # Substack integration
└── prompts/
    ├── story_seeds.yaml        # Story prompts
    └── links_seeds.yaml        # Link categories
```

## Environment Variables

### GitHub Secrets
```yaml
OPENAI_API_KEY:          # OpenAI API access
OPENAI_API_BASE:         # API endpoint (NVIDIA)
OPENAI_MODEL:            # Model name
# Note: Substack secrets removed - Cloudflare blocks CI
```

### Local Development
```bash
export OPENAI_API_KEY="..."
export OPENAI_API_BASE="https://integrate.api.nvidia.com/v1"
export OPENAI_MODEL="nvidia/llama-3.3-nemotron-super-49b-v1.5"
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
- API calls: 2 per day (story + links)

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
