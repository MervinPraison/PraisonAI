"""Social Media Cross-Posting Agent Example.

Demonstrates using PraisonAI Agent with all social media tools
to cross-post content across multiple platforms.

Required environment variables (set only the ones you need):
    # X (Twitter)
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET

    # LinkedIn
    LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN

    # Facebook
    FACEBOOK_PAGE_ACCESS_TOKEN, FACEBOOK_PAGE_ID

    # Instagram
    INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID

    # TikTok
    TIKTOK_ACCESS_TOKEN

    # Threads
    THREADS_ACCESS_TOKEN, THREADS_USER_ID

    # Pinterest
    PINTEREST_ACCESS_TOKEN

    # Medium
    MEDIUM_TOKEN

    # WordPress (uses praisonaiwp-cli config — no env vars needed)

    # OpenAI (for the agent)
    OPENAI_API_KEY

Usage:
    python social_media_crosspost.py
"""

from praisonaiagents import Agent

from praisonai_tools import (
    # X (Twitter)
    post_to_x,
    # LinkedIn
    linkedin_post_text,
    linkedin_post_image,
    linkedin_post_article,
    # Facebook
    facebook_post_text,
    facebook_post_image,
    facebook_post_link,
    # Instagram
    instagram_post_image,
    instagram_post_reel,
    # TikTok
    tiktok_post_video,
    tiktok_post_photo,
    # Threads
    threads_post_text,
    threads_post_image,
    # Pinterest
    pinterest_create_pin,
    pinterest_list_boards,
    # Medium
    medium_publish_post,
    # WordPress
    create_wp_post,
    check_wp_duplicate,
)

# Create a social media manager agent
agent = Agent(
    name="Social Media Manager",
    instructions="""You are a social media manager. You help users cross-post content
    across multiple platforms including X (Twitter), LinkedIn, Facebook, Instagram,
    TikTok, Threads, Pinterest, Medium, and WordPress.

    When asked to cross-post:
    1. Adapt the content format for each platform (character limits, hashtags, etc.)
    2. Use the appropriate tool for each platform
    3. Report which platforms succeeded and which had errors

    Platform-specific notes:
    - X: 280 char limit
    - LinkedIn: 3000 char limit, professional tone
    - Facebook: No strict limit, supports links
    - Instagram: Needs image URL (public URL), max 2200 chars caption
    - TikTok: Video/photo only, 150 char title
    - Threads: 500 char limit
    - Pinterest: Needs board_id and image URL
    - Medium: Full article support (markdown/HTML), default to 'draft' status
    - WordPress: Full article support (HTML/Gutenberg blocks), check duplicates first
    """,
    tools=[
        post_to_x,
        linkedin_post_text,
        linkedin_post_image,
        linkedin_post_article,
        facebook_post_text,
        facebook_post_image,
        facebook_post_link,
        instagram_post_image,
        instagram_post_reel,
        tiktok_post_video,
        tiktok_post_photo,
        threads_post_text,
        threads_post_image,
        pinterest_create_pin,
        pinterest_list_boards,
        medium_publish_post,
        create_wp_post,
        check_wp_duplicate,
    ],
)

# Example: Post to all text-based platforms
result = agent.start(
    "Post this announcement to LinkedIn and Threads: "
    "'PraisonAI v2.0 is here! Build AI agents in 3 lines of code. "
    "Multi-agent workflows, memory, tools, and more. Try it: pip install praisonaiagents'"
)
print(result)
