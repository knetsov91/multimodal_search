"""
Playwright demo: deleting a recipe as admin, with Attu (Milvus data browser)
and the MinIO console used to verify the underlying data before deletion.
Covers: admin login, search, confirm the record exists in Milvus and the
image exists in MinIO, delete the recipe, then confirm it's gone from both
Milvus and MinIO.
Runs the app, Attu and MinIO in separate browser tabs, switching between
them, so none of them loses its state while the others are used.
Runs fullscreen (no OS bar) via --start-fullscreen flag.
Saves the session as recipe_delete_demo.gif using async screenshot capture.
"""
import asyncio
import io
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from PIL import Image

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

BASE_URL  = "http://localhost:8081"
ATTU_URL  = "http://localhost:8001/#/databases/default/cooking_3000/data"
MINIO_URL = "http://localhost:9001/browser/images"
MINIO_USER     = os.environ["MINIO_USER"]
MINIO_PASSWORD = os.environ["MINIO_PASSWORD"]
GIF_OUT   = ROOT_DIR / "assets" / "recipe_delete_demo.gif"

RECIPE_TITLE = "Rainbow Layer Cake"
QUERY_EXPR   = 'img_name == "cake.jpg"'

SEARCH_TIMEOUT = 30_000
NAV_TIMEOUT    = 10_000
CAPTURE_FPS    = 5
GIF_WIDTH      = 1280
GIF_HEIGHT     = 720

# Playwright's synthetic mouse events don't render an OS cursor, so clicks
# otherwise look like the page just teleports into its new state — this
# draws a fake cursor arrow that follows real mousemove events.
CURSOR_INIT_SCRIPT = """
(() => {
    const cursor = document.createElement('div');
    cursor.id = '__demo_cursor';
    cursor.style.position = 'fixed';
    cursor.style.top = '0';
    cursor.style.left = '0';
    cursor.style.width = '16px';
    cursor.style.height = '22px';
    cursor.style.pointerEvents = 'none';
    cursor.style.zIndex = '2147483647';
    cursor.style.background = '#000';
    cursor.style.clipPath = 'polygon(0 0, 0 100%, 35% 72%, 52% 100%, 68% 92%, 50% 62%, 100% 62%)';
    cursor.style.filter = 'drop-shadow(1px 0 0 #fff) drop-shadow(-1px 0 0 #fff) '
        + 'drop-shadow(0 1px 0 #fff) drop-shadow(0 -1px 0 #fff)';
    const attach = () => document.body && document.body.appendChild(cursor);
    document.addEventListener('DOMContentLoaded', attach);
    window.addEventListener('load', attach);
    document.addEventListener('mousemove', (e) => {
        cursor.style.left = e.clientX + 'px';
        cursor.style.top = e.clientY + 'px';
    }, true);
})();
"""


async def capture_loop(active: dict, frames: list, stop: asyncio.Event):
    interval = 1 / CAPTURE_FPS
    while not stop.is_set():
        try:
            png = await active["page"].screenshot()
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
        f.quantize(colors=256, method=Image.Quantize.MEDIANCUT) for f in frames
    ]
    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=1000 // CAPTURE_FPS,
        loop=0,
        optimize=False,
    )
    print(f"Saved: {path} ({path.stat().st_size / 1_048_576:.1f} MB)")


async def run(pw):
    browser = await pw.chromium.launch(
        headless=False,
        slow_mo=250,
        args=["--start-fullscreen"],
    )
    ctx = await browser.new_context(viewport={"width": GIF_WIDTH, "height": GIF_HEIGHT})
    await ctx.add_init_script(CURSOR_INIT_SCRIPT)
    app_page = await ctx.new_page()
    attu_page = await ctx.new_page()
    minio_page = await ctx.new_page()
    await app_page.bring_to_front()

    active = {"page": app_page}
    frames: list[Image.Image] = []
    stop = asyncio.Event()
    capture_task = asyncio.create_task(capture_loop(active, frames, stop))

    async def slow(ms: int = 1500):
        await asyncio.sleep(ms / 1000)

    async def switch_to(page):
        active["page"] = page
        await page.bring_to_front()
        await slow(600)

    async def click_visibly(page, locator):
        box = await locator.bounding_box()
        if box:
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=25)
            await slow(400)
        await locator.click()

    async def wait_for_search():
        await app_page.wait_for_function(
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

    async def search_text(query: str):
        await app_page.goto(BASE_URL, timeout=NAV_TIMEOUT)
        await app_page.wait_for_load_state("networkidle")
        await slow(800)
        await app_page.fill("input[name='text_query']", query)
        await slow(1000)
        await app_page.click("#search_btn")
        await wait_for_search()
        await slow(1000)

    exact_title = re.compile(rf"^{re.escape(RECIPE_TITLE)}$")

    def recipe_card():
        return app_page.locator(".recipe", has=app_page.locator("h1", has_text=exact_title))

    async def attu_connect():
        await attu_page.goto(ATTU_URL, timeout=NAV_TIMEOUT)
        await attu_page.wait_for_load_state("networkidle")
        await slow(1000)
        connect_btn = attu_page.locator("button:has-text('Connect')")
        if await connect_btn.count() > 0:
            await connect_btn.first.click(timeout=3000)
            await attu_page.wait_for_load_state("networkidle")
            await slow(1500)
            await attu_page.goto(ATTU_URL, timeout=NAV_TIMEOUT)
            await attu_page.wait_for_load_state("networkidle")
            await slow(1500)

    async def attu_table_text() -> str:
        return await attu_page.locator("table tbody").first.inner_text()

    async def attu_query(expression: str):
        box = attu_page.locator(".cm-content")
        await box.click()
        await attu_page.keyboard.press("Control+A")
        await attu_page.keyboard.press("Delete")
        await attu_page.keyboard.type(expression)
        await slow(400)
        # Attu's result table sometimes doesn't paint on the first Query
        # click even though the API already returned data — the same query
        # succeeds when resubmitted, so retry the click a few times.
        for _ in range(4):
            await attu_page.click("button:has-text('Query')")
            await slow(1500)
            if "No Result" not in await attu_table_text():
                return

    async def wait_attu_empty(expression: str, timeout: float, poll: float) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await attu_query(expression)
            if "No Result" in await attu_table_text():
                return True
            await asyncio.sleep(poll)
        return False

    async def minio_browse_images():
        await minio_page.goto(MINIO_URL, timeout=NAV_TIMEOUT)
        await minio_page.wait_for_load_state("networkidle")
        await slow(1000)
        if "/login" in minio_page.url:
            await minio_page.fill("input[name='accessKey']", MINIO_USER)
            await slow(500)
            await minio_page.fill("input[name='secretKey']", MINIO_PASSWORD)
            await slow(500)
            await minio_page.click("button:has-text('Login')")
            await minio_page.wait_for_load_state("networkidle")
            await slow(1500)
            await minio_page.goto(MINIO_URL, timeout=NAV_TIMEOUT)
            await minio_page.wait_for_load_state("networkidle")
            await slow(1000)

    async def minio_filter(query: str):
        await minio_page.fill("input[placeholder='Start typing to filter objects in the bucket']", query)
        await slow(1200)

    async def wait_minio_gone(query: str, timeout: float, poll: float) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await minio_browse_images()
            await minio_filter(query)
            if await minio_page.get_by_text(query).count() == 0:
                return True
            await asyncio.sleep(poll)
        return False

    # ── 1. Admin login ────────────────────────────────────────────────────────
    print("→ Login as admin")
    await app_page.goto(f"{BASE_URL}/login", timeout=NAV_TIMEOUT)
    await app_page.wait_for_load_state("networkidle")
    await slow()
    await app_page.fill("input[name='email']", "admin")
    await slow(600)
    await app_page.fill("input[name='password']", "admin")
    await slow(600)
    await app_page.click("button[type='submit']")
    await app_page.wait_for_url(f"{BASE_URL}/admin", timeout=NAV_TIMEOUT)
    await slow()

    # ── 2. Search for the cake ───────────────────────────────────────────────
    print(f"→ Search: '{RECIPE_TITLE}'")
    await search_text(RECIPE_TITLE)
    print(f"   Found {await recipe_card().count()} match(es)")
    await slow(2000)

    # ── 3. Attu (separate tab): confirm the record exists ───────────────────
    print("→ Attu: record exists before delete")
    await attu_connect()
    await switch_to(attu_page)
    await attu_query(QUERY_EXPR)
    before_text = await attu_table_text()
    print(f"   {before_text[:80]}")
    await slow(2500)

    # ── 4. MinIO (separate tab): confirm the image exists ───────────────────
    print("→ MinIO: image exists before delete")
    await switch_to(minio_page)
    await minio_browse_images()
    await minio_filter("cake.jpg")
    found = await minio_page.get_by_text("cake.jpg").count() > 0
    print(f"   File visible in MinIO: {found}")
    await slow(2500)

    # ── 5. Back to the app: delete the recipe ────────────────────────────────
    print("→ Delete recipe")
    await switch_to(app_page)
    await click_visibly(app_page, recipe_card().locator("button:has-text('Delete')"))
    await slow(1500)
    await app_page.wait_for_load_state("networkidle")
    await slow(1000)

    # ── 6. Attu: confirm the record is gone ──────────────────────────────────
    print("→ Attu: confirm record deleted")
    await switch_to(attu_page)
    gone = await wait_attu_empty(QUERY_EXPR, 15.0, 2.0)
    print(f"   Deleted from Milvus: {gone}")
    await slow(2500)

    # ── 7. MinIO: confirm the image is gone ──────────────────────────────────
    print("→ MinIO: confirm image deleted")
    await switch_to(minio_page)
    minio_gone = await wait_minio_gone("cake.jpg", 15.0, 2.0)
    print(f"   Deleted from MinIO: {minio_gone}")
    await slow(2500)

    # ── 8. Back to the app: recipe no longer found ────────────────────────────
    print(f"→ Search again: '{RECIPE_TITLE}' (verify it's gone)")
    await switch_to(app_page)
    await search_text(RECIPE_TITLE)
    count = await recipe_card().count()
    print(f"   {count} result(s) matching title — should be 0")
    await slow(2500)

    print("→ Demo complete. Keeping browser open for 3 s…")
    await slow(3000)

    stop.set()
    await capture_task
    await browser.close()
    save_gif(frames, GIF_OUT)


async def main():
    async with async_playwright() as pw:
        await run(pw)


if __name__ == "__main__":
    asyncio.run(main())
