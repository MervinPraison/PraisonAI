"""
Browser Benchmark Module for PraisonAI.

Tests browser automation accuracy and efficiency:
- Tracks ideal steps vs actual steps
- Measures success rate across test scenarios
- Compares different modes (CDP, Extension, Hybrid)
- Records retry counts and failure reasons

Usage:
    praisonai browser benchmark run          # Run all benchmarks
    praisonai browser benchmark quick        # Quick test (3 scenarios)
    praisonai browser benchmark report       # Show last results

Test Scenarios (with ideal step counts):
    - Simple navigation (1-2 steps)
    - Search and click (3-5 steps)
    - Multi-page navigation (5-10 steps)
    - Form filling (4-6 steps)
    - Complex SPA interaction (8-15 steps)
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import statistics

logger = logging.getLogger("praisonai.browser.benchmark")


@dataclass
class BrowserTestCase:
    """A single browser test case."""
    name: str
    goal: str
    url: str
    ideal_steps: int  # Expected number of steps for a human/ideal agent
    max_steps: int = 20  # Max allowed steps
    category: str = "general"  # simple, search, navigation, form, spa
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "goal": self.goal,
            "url": self.url,
            "ideal_steps": self.ideal_steps,
            "max_steps": self.max_steps,
            "category": self.category,
        }


@dataclass
class BrowserTestResult:
    """Result of a single browser test."""
    test_case: BrowserTestCase
    success: bool
    actual_steps: int
    total_retries: int = 0
    duration_ms: float = 0.0
    final_url: str = ""
    summary: str = ""
    error: str = ""
    session_id: str = ""
    engine: str = "cdp"
    video_url: str = ""  # Path to recorded video (WebM)
    screenshots_dir: str = ""  # Directory with step screenshots
    
    @property
    def efficiency(self) -> float:
        """Efficiency = ideal_steps / actual_steps (higher is better, max 1.0)"""
        if self.actual_steps == 0:
            return 0.0
        return min(1.0, self.test_case.ideal_steps / self.actual_steps)
    
    @property
    def step_overhead(self) -> int:
        """Extra steps beyond ideal (negative = better than expected)"""
        return self.actual_steps - self.test_case.ideal_steps
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_case": self.test_case.to_dict(),
            "success": self.success,
            "actual_steps": self.actual_steps,
            "ideal_steps": self.test_case.ideal_steps,
            "step_overhead": self.step_overhead,
            "efficiency": round(self.efficiency, 2),
            "total_retries": self.total_retries,
            "duration_ms": round(self.duration_ms, 2),
            "final_url": self.final_url,
            "summary": self.summary,
            "error": self.error,
            "session_id": self.session_id,
            "engine": self.engine,
            "video_url": self.video_url,
            "screenshots_dir": self.screenshots_dir,
        }


@dataclass
class BrowserBenchmarkReport:
    """Aggregated browser benchmark results."""
    timestamp: str
    engine: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    results: List[BrowserTestResult] = field(default_factory=list)
    
    # Aggregated metrics
    success_rate: float = 0.0
    mean_efficiency: float = 0.0
    mean_step_overhead: float = 0.0
    total_retries: int = 0
    mean_duration_ms: float = 0.0
    
    # By category
    category_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def compute_stats(self):
        """Compute aggregated statistics."""
        if not self.results:
            return
        
        self.total_tests = len(self.results)
        self.passed_tests = sum(1 for r in self.results if r.success)
        self.failed_tests = self.total_tests - self.passed_tests
        
        self.success_rate = self.passed_tests / self.total_tests if self.total_tests > 0 else 0.0
        
        successful = [r for r in self.results if r.success]
        if successful:
            self.mean_efficiency = statistics.mean([r.efficiency for r in successful])
            self.mean_step_overhead = statistics.mean([r.step_overhead for r in successful])
            self.mean_duration_ms = statistics.mean([r.duration_ms for r in successful])
        
        self.total_retries = sum(r.total_retries for r in self.results)
        
        # By category
        categories: Dict[str, List[BrowserTestResult]] = {}
        for r in self.results:
            cat = r.test_case.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r)
        
        for cat, results in categories.items():
            passed = [r for r in results if r.success]
            self.category_stats[cat] = {
                "total": len(results),
                "passed": len(passed),
                "success_rate": len(passed) / len(results) if results else 0,
                "mean_efficiency": statistics.mean([r.efficiency for r in passed]) if passed else 0,
                "mean_overhead": statistics.mean([r.step_overhead for r in passed]) if passed else 0,
            }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "engine": self.engine,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "success_rate": round(self.success_rate, 2),
            "mean_efficiency": round(self.mean_efficiency, 2),
            "mean_step_overhead": round(self.mean_step_overhead, 2),
            "total_retries": self.total_retries,
            "mean_duration_ms": round(self.mean_duration_ms, 2),
            "category_stats": self.category_stats,
            "results": [r.to_dict() for r in self.results],
        }


# Standard test scenarios with ideal step counts
BROWSER_TEST_SCENARIOS: List[BrowserTestCase] = [
    # Simple navigation (1-2 steps)
    BrowserTestCase(
        name="Simple Navigation - Google",
        goal="Go to google.com and confirm the page loaded",
        url="https://www.google.com",
        ideal_steps=1,
        category="simple",
    ),
    BrowserTestCase(
        name="Simple Navigation - Wikipedia",
        goal="Go to wikipedia.org and confirm the main page loaded",
        url="https://www.wikipedia.org",
        ideal_steps=1,
        category="simple",
    ),
    
    # Search tasks (3-5 steps)
    BrowserTestCase(
        name="Google Search",
        goal="""Complete these steps:
1. Type "PraisonAI" in the search box
2. Press Enter or click Search
3. Confirm search results appeared
Then mark done.""",
        url="https://www.google.com",
        ideal_steps=3,
        category="search",
    ),
    BrowserTestCase(
        name="DuckDuckGo Search",
        goal="""Complete these steps:
1. Type "browser automation" in the search box
2. Click the search button
3. Confirm search results loaded
Then mark done and summarize top results.""",
        url="https://duckduckgo.com",
        ideal_steps=4,
        category="search",
    ),
    
    # Multi-page navigation (5-10 steps)
    BrowserTestCase(
        name="Wikipedia Search + Article",
        goal="""Complete these steps:
1. Search for "Artificial Intelligence" using the search box
2. Click on the main article in search results
3. Scroll down to see the article content
4. Find and click on a section link (e.g., History)
5. Summarize what you found
Then mark done.""",
        url="https://www.wikipedia.org",
        ideal_steps=6,
        category="navigation",
    ),
    BrowserTestCase(
        name="Hacker News Article",
        goal="""Complete these steps:
1. Click on the top story headline
2. Wait for the page/article to load
3. Scroll down to read content
4. Summarize what the article is about
Then mark done.""",
        url="https://news.ycombinator.com",
        ideal_steps=5,
        category="navigation",
    ),
    
    # Search + Click Result (4-6 steps)
    BrowserTestCase(
        name="Google Search + Click",
        goal="""Complete these steps:
1. Type "Python programming language" in search
2. Submit the search
3. Click on the first search result link
4. Wait for the page to load
5. Summarize what the page is about
Then mark done.""",
        url="https://www.google.com",
        ideal_steps=5,
        category="search",
    ),
    
    # Complex SPA (8-15 steps)
    BrowserTestCase(
        name="GitHub Trending",
        goal="""Complete these steps:
1. Navigate to the Explore section (click Explore in nav)
2. Scroll down to find trending repositories
3. Click on one of the trending repository links
4. On the repo page, scroll down to see the README
5. Click on the Issues tab
6. Summarize: repo name, purpose, and number of open issues
Then mark done.""",
        url="https://github.com",
        ideal_steps=8,
        max_steps=20,
        category="spa",
    ),
]

# Quick test subset
QUICK_TEST_SCENARIOS = [
    BROWSER_TEST_SCENARIOS[0],  # Simple - Google
    BROWSER_TEST_SCENARIOS[2],  # Search - Google
    BROWSER_TEST_SCENARIOS[5],  # Navigation - Hacker News
]


class BrowserBenchmark:
    """Browser automation benchmark runner.
    
    Features:
    - Screenshot capture per test
    - Video recording (via extension)
    - CSV file input for custom scenarios
    - Ideal vs actual step tracking
    """
    
    def __init__(
        self,
        engine: str = "cdp",
        port: int = 9222,
        model: str = "gpt-4o-mini",
        verbose: bool = False,
        capture_screenshots: bool = True,
        debug: bool = False,
    ):
        self.engine = engine
        self.port = port
        self.model = model
        self.verbose = verbose
        self.capture_screenshots = capture_screenshots
        self.debug = debug
        self.results_dir = Path.home() / ".praisonai" / "browser_benchmarks"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir = self.results_dir / "videos"
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_base = self.results_dir / "screenshots"
        self.screenshots_base.mkdir(parents=True, exist_ok=True)
        
        # Process references for cleanup
        self._server_process = None
        self._chrome_process = None
        self._temp_profile = None
        self._bridge_port = 8765
    
    async def _check_bridge_server(self) -> bool:
        """Check if bridge server is running."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{self._bridge_port}/health", 
                                       timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    async def _check_cdp_available(self) -> bool:
        """Check if Chrome CDP is available."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{self.port}/json", 
                                       timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        targets = await resp.json()
                        return len(targets) > 0
                    return False
        except Exception:
            return False
    
    async def _ensure_bridge_server(self) -> bool:
        """Ensure bridge server is running, start if not."""
        import subprocess
        import sys
        
        if await self._check_bridge_server():
            if self.verbose:
                print(f"✓ Bridge server already running on port {self._bridge_port}")
            return True
        
        if self.verbose:
            print(f"Starting bridge server on port {self._bridge_port}...")
        
        try:
            self._server_process = subprocess.Popen(
                [sys.executable, "-m", "praisonai.browser.server", "--port", str(self._bridge_port)],
                stdout=subprocess.PIPE if not self.debug else None,
                stderr=subprocess.PIPE if not self.debug else None,
                start_new_session=True,
            )
            
            # Wait for server to start
            for _ in range(10):
                await asyncio.sleep(0.5)
                if await self._check_bridge_server():
                    if self.verbose:
                        print("✓ Bridge server started")
                    return True
            
            print("⚠️ Bridge server may not have started properly")
            return False
            
        except Exception as e:
            print(f"❌ Failed to start bridge server: {e}")
            return False
    
    async def _ensure_chrome_with_extension(self) -> bool:
        """Ensure Chrome is running with the extension loaded."""
        import subprocess
        import platform
        import tempfile
        import os
        
        # First check if CDP is already available with extension
        if await self._check_cdp_available():
            if self.verbose:
                print(f"✓ Chrome already running with CDP on port {self.port}")
            return True
        
        # Find Chrome
        system = platform.system()
        chrome_path = None
        if system == "Darwin":
            for path in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                         "/Applications/Chromium.app/Contents/MacOS/Chromium"]:
                if os.path.exists(path):
                    chrome_path = path
                    break
        elif system == "Linux":
            for name in ["google-chrome", "chromium", "chromium-browser"]:
                import shutil
                path = shutil.which(name)
                if path:
                    chrome_path = path
                    break
        
        if not chrome_path:
            print("❌ Chrome not found")
            return False
        
        # Find extension
        extension_path = None
        candidates = [
            os.path.expanduser("~/praisonai-chrome-extension/dist"),
            str(Path(__file__).parent.parent.parent.parent.parent / "praisonai-chrome-extension" / "dist"),
        ]
        for cand in candidates:
            if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "manifest.json")):
                extension_path = os.path.abspath(cand)
                break
        
        if not extension_path:
            print("❌ Extension not found. Build it with: cd ~/praisonai-chrome-extension && npm run build")
            return False
        
        # Create temp profile
        self._temp_profile = tempfile.mkdtemp(prefix="praisonai_benchmark_")
        
        # Build Chrome args
        chrome_args = [
            chrome_path,
            f"--load-extension={extension_path}",
            f"--disable-extensions-except={extension_path}",  # Critical: only load our extension
            f"--user-data-dir={self._temp_profile}",
            f"--remote-debugging-port={self.port}",
            "--enable-extensions",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-default-apps",
            "--disable-popup-blocking",
            "--disable-translate",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "https://www.google.com",
        ]
        
        if self.verbose:
            print(f"Launching Chrome with extension from {extension_path}...")
        
        try:
            self._chrome_process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.PIPE if not self.debug else None,
                stderr=subprocess.PIPE if not self.debug else None,
            )
            
            # Wait for Chrome to start
            for _ in range(15):
                await asyncio.sleep(0.5)
                if await self._check_cdp_available():
                    if self.verbose:
                        print("✓ Chrome started with extension")
                    return True
            
            print("⚠️ Chrome may not have started properly")
            return False
            
        except Exception as e:
            print(f"❌ Failed to start Chrome: {e}")
            return False
    
    async def _setup_extension_mode(self) -> bool:
        """Setup extension mode infrastructure: bridge server + Chrome with extension."""
        if self.verbose:
            print("\n[Extension Mode Setup]")
        
        # Start bridge server
        if not await self._ensure_bridge_server():
            return False
        
        # Start Chrome with extension
        if not await self._ensure_chrome_with_extension():
            return False
        
        # Wait a bit for extension to initialize
        await asyncio.sleep(2)
        
        if self.verbose:
            print("✓ Extension mode ready\n")
        
        return True
    
    def _cleanup_extension_mode(self):
        """Cleanup extension mode processes."""
        import shutil
        
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                pass
        
        if self._server_process:
            try:
                self._server_process.terminate()
                self._server_process.wait(timeout=5)
            except Exception:
                pass
        
        if self._temp_profile:
            try:
                shutil.rmtree(self._temp_profile, ignore_errors=True)
            except Exception:
                pass
    
    @staticmethod
    def load_from_csv(csv_path: str) -> List[BrowserTestCase]:
        """Load test scenarios from CSV file.
        
        CSV format:
            name,goal,url,ideal_steps,max_steps,category
            
        Example:
            Simple Google,Go to google.com,https://google.com,1,10,simple
        """
        import csv
        scenarios = []
        
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                scenarios.append(BrowserTestCase(
                    name=row.get('name', 'Unnamed Test'),
                    goal=row.get('goal', ''),
                    url=row.get('url', 'https://www.google.com'),
                    ideal_steps=int(row.get('ideal_steps', 3)),
                    max_steps=int(row.get('max_steps', 20)),
                    category=row.get('category', 'custom'),
                ))
        
        if not scenarios:
            raise ValueError(f"No test scenarios found in {csv_path}")
        
        return scenarios
    
    async def run_single_test(self, test_case: BrowserTestCase, test_index: int = 0) -> BrowserTestResult:
        """Run a single test case with screenshot capture."""
        from .cdp_agent import CDPBrowserAgent
        import os
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Running: {test_case.name}")
            print(f"Goal: {test_case.goal[:60]}...")
            print(f"Ideal steps: {test_case.ideal_steps}")
            print(f"{'='*60}")
        
        # Setup screenshots directory for this test
        test_screenshots_dir = None
        if self.capture_screenshots:
            test_safe_name = test_case.name.replace(" ", "_").replace("/", "_")[:30]
            timestamp = datetime.now().strftime("%H%M%S")
            test_screenshots_dir = str(self.screenshots_base / f"{test_index:02d}_{test_safe_name}_{timestamp}")
            os.makedirs(test_screenshots_dir, exist_ok=True)
        
        start_time = time.perf_counter()
        
        try:
            # Choose engine based on configuration
            if self.engine in ("extension", "hybrid"):
                # Use run_hybrid for extension/hybrid mode
                from .cdp_agent import run_hybrid
                if self.verbose:
                    print(f"  Engine: {self.engine} (via run_hybrid)")
                
                result = await run_hybrid(
                    goal=test_case.goal,
                    url=test_case.url,
                    model=self.model,
                    max_steps=test_case.max_steps,
                    verbose=self.verbose,
                    prefer_extension=(self.engine == "extension"),
                )
            else:
                # Use CDP agent directly for cdp mode
                from .cdp_agent import CDPBrowserAgent
                if self.verbose:
                    print(f"  Engine: cdp (CDPBrowserAgent)")
                
                agent = CDPBrowserAgent(
                    port=self.port,
                    model=self.model,
                    max_steps=test_case.max_steps,
                    verbose=self.verbose,
                    max_retries=3,
                    record_session=True,
                    screenshot_dir=test_screenshots_dir,  # Enable screenshot capture
                    debug=self.debug,
                )
                result = await agent.run(test_case.goal, test_case.url)
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Get video URL if available (from session)
            video_url = result.get("video_url", "")
            
            test_result = BrowserTestResult(
                test_case=test_case,
                success=result.get("success", False),
                actual_steps=result.get("steps", 0),
                total_retries=result.get("total_retries", 0),
                duration_ms=duration_ms,
                final_url=result.get("final_url", ""),
                summary=str(result.get("summary", ""))[:200],
                error=result.get("error", ""),
                session_id=result.get("session_id", ""),
                engine=self.engine,
                video_url=video_url,
                screenshots_dir=test_screenshots_dir or "",
            )
            
            if self.verbose:
                status = "✅ PASSED" if test_result.success else "❌ FAILED"
                print(f"\n{status}")
                print(f"  Steps: {test_result.actual_steps} (ideal: {test_case.ideal_steps}, overhead: {test_result.step_overhead:+d})")
                print(f"  Efficiency: {test_result.efficiency:.0%}")
                print(f"  Retries: {test_result.total_retries}")
                print(f"  Duration: {test_result.duration_ms:.0f}ms")
                if test_screenshots_dir:
                    print(f"  Screenshots: {test_screenshots_dir}")
                if video_url:
                    print(f"  Video: {video_url}")
            
            return test_result
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            if self.verbose:
                print(f"\n❌ ERROR: {e}")
            
            return BrowserTestResult(
                test_case=test_case,
                success=False,
                actual_steps=0,
                duration_ms=duration_ms,
                error=str(e),
                engine=self.engine,
                screenshots_dir=test_screenshots_dir or "",
            )

    
    async def run_all_tests(self, scenarios: Optional[List[BrowserTestCase]] = None) -> BrowserBenchmarkReport:
        """Run all test scenarios."""
        if scenarios is None:
            scenarios = BROWSER_TEST_SCENARIOS
        
        # Setup extension mode infrastructure if needed
        needs_extension_setup = self.engine in ("extension", "hybrid")
        if needs_extension_setup:
            if not await self._setup_extension_mode():
                print("❌ Failed to setup extension mode, falling back to CDP")
                self.engine = "cdp"
        
        report = BrowserBenchmarkReport(
            timestamp=datetime.now().isoformat(),
            engine=self.engine,
        )
        
        try:
            for idx, test_case in enumerate(scenarios):
                result = await self.run_single_test(test_case, test_index=idx)
                report.results.append(result)
                
                # Brief pause between tests
                await asyncio.sleep(1)
            
            report.compute_stats()
            
            # Save results
            self._save_report(report)
        finally:
            # Cleanup if we started extension infrastructure
            if needs_extension_setup:
                self._cleanup_extension_mode()
        
        return report
    
    async def run_quick(self) -> BrowserBenchmarkReport:
        """Run quick benchmark (3 key scenarios)."""
        return await self.run_all_tests(QUICK_TEST_SCENARIOS)
    
    def _save_report(self, report: BrowserBenchmarkReport):
        """Save report to results directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.results_dir / f"benchmark_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        
        # Also save as latest
        latest = self.results_dir / "latest.json"
        with open(latest, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        
        if self.verbose:
            print(f"\nResults saved to: {filename}")
    
    def get_last_report(self) -> Optional[BrowserBenchmarkReport]:
        """Load the last benchmark report."""
        latest = self.results_dir / "latest.json"
        if not latest.exists():
            return None
        
        with open(latest) as f:
            data = json.load(f)
        
        # Reconstruct report from JSON
        report = BrowserBenchmarkReport(
            timestamp=data["timestamp"],
            engine=data["engine"],
        )
        report.total_tests = data["total_tests"]
        report.passed_tests = data["passed_tests"]
        report.failed_tests = data["failed_tests"]
        report.success_rate = data["success_rate"]
        report.mean_efficiency = data["mean_efficiency"]
        report.mean_step_overhead = data["mean_step_overhead"]
        report.total_retries = data["total_retries"]
        report.mean_duration_ms = data["mean_duration_ms"]
        report.category_stats = data["category_stats"]
        
        return report
    
    def print_report(self, report: BrowserBenchmarkReport):
        """Print formatted benchmark report with media links."""
        print("\n" + "="*70)
        print("BROWSER BENCHMARK REPORT")
        print("="*70)
        print(f"Timestamp: {report.timestamp}")
        print(f"Engine: {report.engine}")
        print()
        
        # Summary
        print(f"{'SUMMARY':^70}")
        print("-"*70)
        print(f"  Total Tests:      {report.total_tests}")
        print(f"  Passed:           {report.passed_tests} ({report.success_rate:.0%})")
        print(f"  Failed:           {report.failed_tests}")
        print(f"  Mean Efficiency:  {report.mean_efficiency:.0%}")
        print(f"  Mean Overhead:    {report.mean_step_overhead:+.1f} steps")
        print(f"  Total Retries:    {report.total_retries}")
        print(f"  Mean Duration:    {report.mean_duration_ms:.0f}ms")
        print()
        
        # By category
        if report.category_stats:
            print(f"{'BY CATEGORY':^70}")
            print("-"*70)
            print(f"{'Category':<15} {'Pass Rate':<12} {'Efficiency':<12} {'Overhead':<12}")
            print("-"*70)
            for cat, stats in report.category_stats.items():
                print(f"{cat:<15} {stats['success_rate']:.0%} ({stats['passed']}/{stats['total']})   {stats['mean_efficiency']:.0%}           {stats['mean_overhead']:+.1f}")
            print()
        
        # Individual results with media
        print(f"{'INDIVIDUAL RESULTS':^70}")
        print("-"*70)
        print(f"{'Test Name':<30} {'Status':<8} {'Steps':<12} {'Eff':<8}")
        print("-"*70)
        for r in report.results:
            status = "✅" if r.success else "❌"
            steps = f"{r.actual_steps}/{r.test_case.ideal_steps}" if r.success else "N/A"
            eff = f"{r.efficiency:.0%}" if r.success else "-"
            print(f"{r.test_case.name[:28]:<30} {status:<8} {steps:<12} {eff:<8}")
            
            # Show error for failures
            if not r.success and r.error:
                print(f"  └─ Error: {r.error[:60]}")
            
            # Show media links
            if r.screenshots_dir:
                print(f"  📸 Screenshots: {r.screenshots_dir}")
            if r.video_url:
                print(f"  🎬 Video: {r.video_url}")
        
        print("="*70)
        
        # Media summary
        videos = [r for r in report.results if r.video_url]
        screenshots = [r for r in report.results if r.screenshots_dir]
        if videos or screenshots:
            print(f"\n{'MEDIA FILES':^70}")
            print("-"*70)
            if screenshots:
                print(f"  Screenshots: {len(screenshots)} test(s) with screenshots")
                print(f"  Base Dir: {self.screenshots_base}")
            if videos:
                print(f"  Videos: {len(videos)} test(s) with video recording")
            print("="*70)


# CLI commands for browser benchmark
def add_benchmark_commands(app):
    """Add benchmark commands to browser CLI app."""
    import typer
    
    benchmark_app = typer.Typer(help="Browser automation benchmarks")
    
    @benchmark_app.command("run")
    def run_benchmark(
        csv_file: Optional[str] = typer.Argument(None, help="Optional CSV file with test scenarios"),
        quick: bool = typer.Option(False, "--quick", "-q", help="Run quick test (3 scenarios)"),
        verbose: bool = typer.Option(True, "--verbose", "-v", help="Verbose output"),
        engine: str = typer.Option("cdp", "--engine", help="Engine: cdp, extension, hybrid"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
        no_screenshots: bool = typer.Option(False, "--no-screenshots", help="Disable screenshot capture"),
        debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode with detailed logging"),
        record_video: bool = typer.Option(False, "--record-video", help="Create video from screenshots after benchmark"),
    ):
        """Run browser automation benchmark suite.
        
        Examples:
            praisonai browser benchmark run                    # Run all built-in tests
            praisonai browser benchmark run --quick            # Run 3 quick tests
            praisonai browser benchmark run tests.csv          # Run tests from CSV file
            praisonai browser benchmark run --output results.json
        
        CSV Format (with header):
            name,goal,url,ideal_steps,max_steps,category
            My Test,Go to google,https://google.com,1,10,simple
        """
        
        import logging
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logging.getLogger("praisonai.browser.cdp_agent").setLevel(logging.DEBUG)
        
        async def _run():
            benchmark = BrowserBenchmark(
                engine=engine, 
                verbose=verbose,
                capture_screenshots=not no_screenshots,
                debug=debug,
            )
            
            # Load scenarios from CSV or use built-in
            if csv_file:
                try:
                    scenarios = BrowserBenchmark.load_from_csv(csv_file)
                    print(f"Loaded {len(scenarios)} test scenarios from {csv_file}")
                except Exception as e:
                    print(f"Error loading CSV: {e}")
                    return
                report = await benchmark.run_all_tests(scenarios)
            elif quick:
                report = await benchmark.run_quick()
            else:
                report = await benchmark.run_all_tests()
            
            benchmark.print_report(report)
            
            if output:
                with open(output, "w") as f:
                    json.dump(report.to_dict(), f, indent=2)
                print(f"\nJSON results saved to: {output}")
        
        asyncio.run(_run())
    
    @benchmark_app.command("quick")
    def quick_benchmark(
        verbose: bool = typer.Option(True, "--verbose", "-v", help="Verbose output"),
    ):
        """Run quick benchmark (3 key scenarios)."""
        
        async def _run():
            benchmark = BrowserBenchmark(verbose=verbose)
            report = await benchmark.run_quick()
            benchmark.print_report(report)
        
        asyncio.run(_run())
    
    @benchmark_app.command("report")
    def show_report():
        """Show last benchmark results."""
        benchmark = BrowserBenchmark()
        report = benchmark.get_last_report()
        
        if report is None:
            print("No benchmark results found. Run 'praisonai browser benchmark run' first.")
            return
        
        benchmark.print_report(report)
    
    @benchmark_app.command("list")
    def list_scenarios():
        """List all test scenarios."""
        print("\nBrowser Benchmark Test Scenarios")
        print("="*70)
        print(f"{'#':<3} {'Category':<12} {'Name':<35} {'Ideal Steps':<12}")
        print("-"*70)
        
        for i, tc in enumerate(BROWSER_TEST_SCENARIOS, 1):
            print(f"{i:<3} {tc.category:<12} {tc.name[:33]:<35} {tc.ideal_steps:<12}")
        
        print("-"*70)
        print(f"Total: {len(BROWSER_TEST_SCENARIOS)} scenarios")
    
    @benchmark_app.command("template")
    def generate_template(
        output: str = typer.Argument("browser_tests.csv", help="Output CSV filename"),
    ):
        """Generate a CSV template for custom test scenarios.
        
        Example:
            praisonai browser benchmark template my_tests.csv
        """
        import csv
        
        with open(output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Header
            writer.writerow(['name', 'goal', 'url', 'ideal_steps', 'max_steps', 'category'])
            # Example rows
            writer.writerow(['Simple Google', 'Go to google.com and confirm page loaded', 'https://www.google.com', '1', '10', 'simple'])
            writer.writerow(['Google Search', 'Type "PraisonAI" in search box, press Enter, confirm results', 'https://www.google.com', '3', '15', 'search'])
            writer.writerow(['Wikipedia Article', 'Search for AI, click article, scroll down', 'https://www.wikipedia.org', '5', '20', 'navigation'])
        
        print(f"CSV template saved to: {output}")
        print("\nTemplate contains 3 example test scenarios. Edit this file to add your own.")
        print("\nColumns:")
        print("  name        - Test name (displayed in report)")
        print("  goal        - Task description for the browser agent")
        print("  url         - Starting URL")
        print("  ideal_steps - Expected number of steps for ideal completion")
        print("  max_steps   - Maximum allowed steps before failure")
        print("  category    - Test category (simple, search, navigation, form, spa)")
    
    app.add_typer(benchmark_app, name="benchmark")

