---
description: create and publish a post on mer.vin using praisonaiwp
---

## Config

- Server: `default` → `https://mer.vin`
- Config: `~/.praisonaiwp/config.yaml`
- Category for PraisonAI features: `PraisonAI`

---

## Step 1 — Compose the content

Structure every post as:
1. **Intro paragraph** — one sentence, what the feature solves
2. **Mermaid diagram** — architecture/flow (see block format below)
3. **Sections** — H2 headings, tables > prose, code blocks for usage
4. **Performance/summary** — table with concrete numbers

Keep it technical. Lead with diagrams and tables, not paragraphs.

---

## Step 2 — Mermaid block format (merpress)

> **Creating merpress:** Install the [Merpress – Mermaid for WordPress](https://wordpress.org/plugins/merpress/) plugin via `wp plugin install merpress --activate --allow-root` on the server. It adds the `wp:merpress/mermaidjs` block used below.

All posts use the native `wp:merpress/mermaidjs` block. Use this exact format:

```
<!-- wp:merpress/mermaidjs {"align":"full"} -->
<div class="wp-block-merpress-mermaidjs diagram-source-mermaid alignfull"><pre class="mermaid">%%{init: {"theme": "base", "themeVariables": {"background": "transparent", "lineColor": "#000000"}}}%%
graph TD
    A[Input] --> B[Agent]
    B --> C[Tool]
    C --> D[Output]

    classDef hook fill:#189AB4,color:#fff
    classDef agent fill:#8B0000,color:#fff
    classDef decision fill:#444,color:#fff

    class B agent
    class C hook
</pre></div>
<!-- /wp:merpress/mermaidjs -->
```

**Do NOT use:** `[mermaid]...[/mermaid]` shortcode — that is the wrong format.

Color scheme:
- `#8B0000` (dark red) — agents, inputs, outputs
- `#189AB4` (teal) — tools, hooks
- `#444` — decisions/conditionals

---

## Step 2a — SVG/image upload via SSH

`praisonaiwp media upload` correctly SFTPs the file to `/tmp/` on the server, but
`_execute_wp()` in `~/praisonaiwp-cli/praisonaiwp/core/wp_client.py` never appends
`--allow-root`. Use direct SSH instead.

**SVG upload (Safe SVG plugin active on mer.vin):**

```bash
# 1. SCP SVG to server
scp -i ~/.ssh/id_ed25519 /path/to/diagram.svg <SSH_USER>@<SERVER_IP>:/tmp/

# 2. Import via WP-CLI — must pass --user=<admin> so Safe SVG capability check passes
ssh -i ~/.ssh/id_ed25519 <SSH_USER>@<SERVER_IP> \
   "cd <WP_ROOT> && \
    wp media import /tmp/diagram.svg --post_id=<POST_ID> \
    --title='Title' --alt='Alt' --user=praison --allow-root --porcelain"
# → returns media ID

# 3. Get the URL
ssh -i ~/.ssh/id_ed25519 <SSH_USER>@<SERVER_IP> \
   "cd <WP_ROOT> && \
    wp post get <MEDIA_ID> --field=guid --allow-root"
```

> **Key:** `--user=praison` is required — Safe SVG checks upload capability against the
> current WP user. Without it, even with the plugin active, SVG imports are blocked.

**PNG fallback (if Safe SVG not available):**

```bash
rsvg-convert -w 1360 /path/to/diagram.svg -o /tmp/diagram_2x.png
# Then follow the same SSH steps above using the .png file (no --user needed)
```

Use this Gutenberg image block in the post content:

```
<!-- wp:image {"id":<MEDIA_ID>,"sizeSlug":"full","linkDestination":"none"} -->
<figure class="wp-block-image size-full"><img src="<IMAGE_URL>" alt="Alt text" class="wp-image-<MEDIA_ID>"/></figure>
<!-- /wp:image -->
```

---

## Step 3 — Create the post

```bash
praisonaiwp create "Post Title" \
  --status publish \
  --content '<FULL GUTENBERG CONTENT>'
```

Note the returned **Post ID** from the output.

---

## Step 4 — Set category

```bash
praisonaiwp update <POST_ID> --category "PraisonAI"
```

---

## Step 5 — Validate mermaid format

```bash
ssh -i ~/.ssh/id_ed25519 <SSH_USER>@<SERVER_IP> \
   "cd <WP_ROOT> && \
    wp post get <POST_ID> --field=post_content --allow-root | grep -i mermaid"
```

Expected output must contain `wp:merpress/mermaidjs`, not `[mermaid]`.

---

## Key Gutenberg blocks reference

```
<!-- wp:paragraph --><p>text</p><!-- /wp:paragraph -->

<!-- wp:heading --><h2 class="wp-block-heading">Title</h2><!-- /wp:heading -->

<!-- wp:heading {"level":3} --><h3 class="wp-block-heading">Sub</h3><!-- /wp:heading -->

<!-- wp:code --><pre class="wp-block-code"><code>code here</code></pre><!-- /wp:code -->

<!-- wp:table -->
<figure class="wp-block-table"><table>
<thead><tr><th>Col</th></tr></thead>
<tbody><tr><td>Val</td></tr></tbody>
</table></figure>
<!-- /wp:table -->

<!-- wp:list --><ul class="wp-block-list"><li>item</li></ul><!-- /wp:list -->

<!-- wp:separator --><hr class="wp-block-separator has-alpha-channel-opacity"/><!-- /wp:separator -->
```

---

## Full example command

```bash
praisonaiwp create "Feature Name: What It Does" \
  --status publish \
  --content '<!-- wp:paragraph -->
<p>One sentence intro.</p>
<!-- /wp:paragraph -->

<!-- wp:heading -->
<h2 class="wp-block-heading">Architecture</h2>
<!-- /wp:heading -->

<!-- wp:merpress/mermaidjs {"align":"full"} -->
<div class="wp-block-merpress-mermaidjs diagram-source-mermaid alignfull"><pre class="mermaid">%%{init: {"theme": "base", "themeVariables": {"background": "transparent", "lineColor": "#000000"}}}%%
graph TD
    A[Start] --> B[Agent]
    class B agent
    classDef agent fill:#8B0000,color:#fff
</pre></div>
<!-- /wp:merpress/mermaidjs -->

<!-- wp:code -->
<pre class="wp-block-code"><code>from praisonaiagents import Agent
agent = Agent(name="example")
result = agent.start("task")</code></pre>
<!-- /wp:code -->'

# Then set category:
praisonaiwp update <ID> --category "PraisonAI"
```
