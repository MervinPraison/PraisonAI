"""Motion Graphics — Basic HTML/GSAP → MP4 render (no LLM required).

This example drives the `HtmlRenderBackend` directly with a hand-authored
HTML/GSAP composition. It renders to a real MP4 via headless Chromium +
bundled ffmpeg, with no API keys needed.

Requirements:
    pip install praisonai-tools[video-motion]
    playwright install chromium

Verified end-to-end: produces 1920x1080 @ 30fps H.264 MP4 in ~5–10 seconds.
"""

import asyncio
from pathlib import Path

from praisonai_tools.video.motion_graphics import HtmlRenderBackend, RenderOpts


HTML = """
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
  <style>
    body { margin:0; padding:0; background:#0f172a; overflow:hidden;
           font-family: -apple-system, Arial, sans-serif; }
    #stage { width:1920px; height:1080px; position:relative; }
    .title { font-size:96px; font-weight:800; color:#f8fafc;
             position:absolute; top:50%; left:50%;
             transform:translate(-50%,-50%); opacity:0; }
    .subtitle { font-size:44px; color:#94a3b8;
                position:absolute; top:62%; left:50%;
                transform:translate(-50%,-50%); opacity:0; }
    .dot { width:32px; height:32px; border-radius:50%; background:#38bdf8;
           position:absolute; top:78%; left:50%;
           transform:translate(-50%,-50%); opacity:0; }
  </style>
</head>
<body>
  <div id="stage" data-duration="4.0">
    <div class="title">PraisonAI</div>
    <div class="subtitle">Motion Graphics Pipeline</div>
    <div class="dot"></div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.to(".title",    { duration: 0.8, opacity: 1, y: -30, ease: "power3.out" })
      .to(".subtitle", { duration: 0.7, opacity: 1, y: -20, ease: "power3.out" }, "-=0.3")
      .to(".dot",      { duration: 0.5, opacity: 1, scale: 2, ease: "back.out(2)" }, "-=0.2")
      .to(".dot",      { duration: 0.4, x: 200,  ease: "power2.inOut" })
      .to(".dot",      { duration: 0.4, x: -200, ease: "power2.inOut" })
      .to(".dot",      { duration: 0.4, x: 0,    ease: "power2.inOut" })
      .to([".title",".subtitle",".dot"],
          { duration: 0.5, opacity: 0, ease: "power2.in" });
    // Required: export timeline(s) for the render backend to drive.
    window.__timelines = [tl];
  </script>
</body>
</html>
"""


async def main() -> None:
    out = Path("/tmp/motion_graphics_demo")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(HTML)

    backend = HtmlRenderBackend(base_dir=out)

    lint = await backend.lint(out)
    print(f"Lint:   ok={lint.ok}  messages={lint.messages}")

    opts = RenderOpts(output_name="praisonai_demo.mp4", fps=30, quality="standard")
    print("Render: ...", flush=True)
    result = await backend.render(out, opts)

    if result.ok:
        print(f"Render: OK  path={result.output_path}  size={result.size_kb} KB")
    else:
        print(f"Render: FAIL  stderr={result.stderr}")


if __name__ == "__main__":
    asyncio.run(main())
