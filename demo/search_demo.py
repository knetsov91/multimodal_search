"""
Demo 1: multimodal search — text, image, and combined pizza search.
Saves result as search.gif.
"""
import asyncio
import io
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image

ROOT_DIR    = Path(__file__).parent.parent
BASE_URL    = "http://localhost:8081"
PIZZA_IMG   = str(ROOT_DIR / "pizza.jpg")
GIF_OUT     = ROOT_DIR / "assets" / "text_image_combined_search.gif"
SEARCH_TIMEOUT = 30_000
NAV_TIMEOUT    = 10_000
CAPTURE_FPS    = 4
GIF_WIDTH      = 1280
GIF_HEIGHT     = 720


async def capture_loop(page, frames: list, stop: asyncio.Event):
    interval = 1 / CAPTURE_FPS
    while not stop.is_set():
        try:
            png = await page.screenshot()
            img = Image.open(io.BytesIO(png)).convert("RGB")
            img = img.resize((GIF_WIDTH, GIF_HEIGHT), Image.LANCZOS)
            frames.append(img)
        except Exception:
            pass
        await asyncio.sleep(interval)


def save_gif(frames: list[Image.Image], path: Path):
    if not frames:
        print("No frames captured.")
        return
    print(f"Saving {len(frames)} frames → {path}")
    palette_frames = [
        f.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames
    ]
    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=1000 // CAPTURE_FPS,
        loop=0,
        optimize=True,
    )
    print(f"Saved: {path} ({path.stat().st_size / 1_048_576:.1f} MB)")


async def wait_for_search(page):
    await page.wait_for_function(
        """() => {
            const loading = document.getElementById('loading');
            const results = document.querySelectorAll('#results .recipe');
            const error = document.querySelector('#container > p');
            return (loading && loading.style.display === 'none') ||
                   results.length > 0 ||
                   (error && error.innerText !== '');
        }""",
        timeout=SEARCH_TIMEOUT,
    )


async def slow_scroll(page, to_bottom: bool, duration_ms: int = 2000):
    target = "document.body.scrollHeight" if to_bottom else "0"
    await page.evaluate(f"""
        () => new Promise(resolve => {{
            const start = window.scrollY;
            const end = {target};
            const distance = (typeof end === 'number' ? end : document.body.scrollHeight) - start;
            const startTime = performance.now();
            function step(now) {{
                const t = Math.min((now - startTime) / {duration_ms}, 1);
                const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;
                window.scrollTo(0, start + distance * ease);
                if (t < 1) requestAnimationFrame(step);
                else resolve();
            }}
            requestAnimationFrame(step);
        }})
    """)


async def scroll_results(page):
    await asyncio.sleep(0.8)
    await slow_scroll(page, to_bottom=True, duration_ms=4000)
    await asyncio.sleep(1.5)
    await slow_scroll(page, to_bottom=False, duration_ms=3000)
    await asyncio.sleep(1.0)


async def run(pw):
    browser = await pw.chromium.launch(
        headless=False,
        slow_mo=120,
        args=["--start-fullscreen"],
    )
    ctx = await browser.new_context(viewport={"width": GIF_WIDTH, "height": GIF_HEIGHT})
    page = await ctx.new_page()

    frames: list[Image.Image] = []
    stop = asyncio.Event()
    capture_task = asyncio.create_task(capture_loop(page, frames, stop))

    # ── 1. Home page ──────────────────────────────────────────────────────────
    print("→ Home page")
    await page.goto(BASE_URL, timeout=NAV_TIMEOUT)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.0)

    # ── 2. Text search ────────────────────────────────────────────────────────
    print("→ Text search: 'pizza'")
    await page.fill("input[name='text_query']", "pizza")
    await asyncio.sleep(0.8)
    await page.click("#search_btn")
    await wait_for_search(page)
    await asyncio.sleep(0.6)
    count = await page.locator("#results .recipe").count()
    print(f"   {count} result(s)")
    await scroll_results(page)

    # ── 3. Clear ──────────────────────────────────────────────────────────────
    print("→ Clear")
    await page.click("#reset-btn")
    await asyncio.sleep(0.8)

    # ── 4. Image search ───────────────────────────────────────────────────────
    print("→ Image search: pizza.jpg")
    await page.set_input_files("input[type='file']", PIZZA_IMG)
    await asyncio.sleep(0.8)
    await page.click("#search_btn")
    await wait_for_search(page)
    await asyncio.sleep(0.6)
    count = await page.locator("#results .recipe").count()
    print(f"   {count} result(s)")
    await scroll_results(page)

    # ── 5. Clear ──────────────────────────────────────────────────────────────
    print("→ Clear")
    await page.click("#reset-btn")
    await asyncio.sleep(0.8)

    # ── 6. Multimodal search (text + image) ───────────────────────────────────
    print("→ Multimodal search: 'pizza' + pizza.jpg")
    await page.fill("input[name='text_query']", "pizza")
    await asyncio.sleep(0.5)
    await page.set_input_files("input[type='file']", PIZZA_IMG)
    await asyncio.sleep(0.8)
    await page.click("#search_btn")
    await wait_for_search(page)
    await asyncio.sleep(0.6)
    count = await page.locator("#results .recipe").count()
    print(f"   {count} result(s)")
    await scroll_results(page)

    # ── Done ──────────────────────────────────────────────────────────────────
    await asyncio.sleep(2.0)
    stop.set()
    await capture_task
    await browser.close()
    save_gif(frames, GIF_OUT)


async def main():
    async with async_playwright() as pw:
        await run(pw)


if __name__ == "__main__":
    asyncio.run(main())
