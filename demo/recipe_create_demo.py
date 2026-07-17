"""
Playwright demo: multimodal recipe search system.
Covers: text search, image search, then recipe creation — before creating,
MinIO, Attu (Milvus) and Flower (Celery) are each checked in their own tab
to confirm the image, record and task don't exist yet; then an admin logs
in, adjusts settings and creates the recipe; then all three are checked
again to confirm the image, record and task now exist.
Runs the app, Attu, MinIO and Flower in separate browser tabs, switching
between them, so none of them loses its state while the others are used.
Runs fullscreen (no OS bar) via --start-fullscreen flag.
Saves the session as recipe_create_demo.gif using async screenshot capture.
"""
import asyncio
import io
import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from PIL import Image

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

BASE_URL  = "http://localhost:8081"
ATTU_URL  = "http://localhost:8001/#/databases/default/cooking_3000/data"
MINIO_URL = "http://localhost:9001/browser/images"
FLOWER_URL = "http://localhost:5555/tasks"
MINIO_USER     = os.environ["MINIO_USER"]
MINIO_PASSWORD = os.environ["MINIO_PASSWORD"]

CAKE_IMG  = str(ROOT_DIR / "cake.jpg")
GIF_OUT   = ROOT_DIR / "assets" / "recipe_create_demo.gif"

CAKE_QUERY_EXPR = 'img_name == "cake.jpg"'
RECIPE_TITLE = "Rainbow Layer Cake"
RECIPE_TEXT  = "Layered vanilla sponge cake with rainbow colors and cream cheese frosting."

SEARCH_TIMEOUT     = 30_000
NAV_TIMEOUT        = 10_000
UPLOAD_TIMEOUT     = 15_000
CAPTURE_FPS        = 5
GIF_WIDTH          = 1280
GIF_HEIGHT         = 720
TASK_POLL_TIMEOUT  = 30.0
TASK_POLL_INTERVAL = 3.0

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
    flower_page = await ctx.new_page()
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

    async def hover_visibly(page, locator):
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        if box:
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=25)

    async def click_visibly(page, locator):
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        if box:
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            await page.mouse.move(x, y, steps=25)
            await slow(800)
            await page.mouse.click(x, y)
        else:
            await locator.click()

    results = app_page.locator("#results .recipe")

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

    async def scroll_results():
        await slow(1200)
        await app_page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
        await slow(2500)
        await app_page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await slow(1500)

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

    flower_visited = False

    async def flower_show_tasks():
        nonlocal flower_visited
        if not flower_visited:
            await flower_page.goto(FLOWER_URL, timeout=NAV_TIMEOUT)
            flower_visited = True
        else:
            await flower_page.reload(timeout=NAV_TIMEOUT)
        await flower_page.wait_for_load_state("networkidle")
        await slow(1500)

    async def flower_snapshot() -> str:
        try:
            return await flower_page.locator("table tbody").first.inner_text()
        except Exception:
            return ""

    async def wait_flower_new_task(prev_snapshot: str, timeout: float, poll: float) -> bool:
        # Flower learns about a task from a broker event, which can lag a
        # moment behind the request that enqueued it — a single reload right
        # after submitting isn't reliable, so poll-reload until the table
        # actually differs from the pre-upload snapshot.
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await flower_page.reload(timeout=NAV_TIMEOUT)
            await flower_page.wait_for_load_state("networkidle")
            snap = await flower_snapshot()
            if snap and snap != prev_snapshot:
                return True
            await asyncio.sleep(poll)
        return False

    async def wait_task_success(timeout: float, poll: float) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if "SUCCESS" in await flower_snapshot():
                return True
            await asyncio.sleep(poll)
            await flower_page.reload(timeout=NAV_TIMEOUT)
            await flower_page.wait_for_load_state("networkidle")
        return False

    # ── 1. Home page ──────────────────────────────────────────────────────────
    print("→ Home page")
    await app_page.goto(BASE_URL, timeout=NAV_TIMEOUT)
    await app_page.wait_for_load_state("networkidle")
    await slow()

    # ── 2. Text search ────────────────────────────────────────────────────────
    print(f"→ Text search: '{RECIPE_TITLE}'")
    await app_page.fill("input[name='text_query']", RECIPE_TITLE)
    await slow(1200)
    await click_visibly(app_page, app_page.locator("#search_btn"))
    await wait_for_search()
    await slow(1000)
    print(f"   {await results.count()} result(s)")
    await scroll_results()

    # ── 3. Reset ──────────────────────────────────────────────────────────────
    print("→ Clear")
    await click_visibly(app_page, app_page.locator("#reset-btn"))
    await slow(1200)

    # ── 4. Image search ───────────────────────────────────────────────────────
    print("→ Image search: cake.jpg")
    await app_page.set_input_files("input[type='file']", CAKE_IMG)
    await slow(1000)
    await click_visibly(app_page, app_page.locator("#search_btn"))
    await wait_for_search()
    await slow(1000)
    print(f"   {await results.count()} result(s)")
    await scroll_results()

    # ── 5. MinIO (separate tab): confirm the image doesn't exist yet ────────
    print("→ MinIO: confirm cake.jpg not uploaded yet")
    await switch_to(minio_page)
    await minio_browse_images()
    await minio_filter("cake.jpg")
    found_before = await minio_page.get_by_text("cake.jpg").count() > 0
    print(f"   File visible in MinIO: {found_before}")
    await slow(2000)

    # ── 6. Attu (separate tab): confirm no record exists yet ────────────────
    print("→ Attu: confirm no record for cake.jpg yet")
    await attu_connect()
    await switch_to(attu_page)
    await attu_query(CAKE_QUERY_EXPR)
    before_text = await attu_table_text()
    print(f"   {before_text[:60]}")
    await slow(2000)

    # ── 7. Flower (separate tab): confirm no task exists yet ────────────────
    print("→ Flower: confirm no task yet")
    await switch_to(flower_page)
    await flower_show_tasks()
    flower_before_snapshot = await flower_snapshot()
    await slow(2000)

    # ── 8. Admin login ────────────────────────────────────────────────────────
    print("→ Login as admin")
    await switch_to(app_page)
    await app_page.goto(f"{BASE_URL}/login", timeout=NAV_TIMEOUT)
    await app_page.wait_for_load_state("networkidle")
    await slow()
    await app_page.fill("input[name='email']", "admin")
    await slow(600)
    await app_page.fill("input[name='password']", "admin")
    await slow(600)
    await click_visibly(app_page, app_page.locator("button[type='submit']"))
    await app_page.wait_for_url(f"{BASE_URL}/admin", timeout=NAV_TIMEOUT)
    await slow()

    # ── 9. Admin settings ────────────────────────────────────────────────────
    print("→ Admin settings: alpha=0.5, result_num=8")
    await app_page.wait_for_load_state("networkidle")
    await slow(1200)
    await app_page.locator("select#alpha").scroll_into_view_if_needed()
    await slow(1000)
    await app_page.select_option("select#alpha", "0.5")
    await slow(800)
    await app_page.fill("#settings input#result_num", "8")
    await slow(800)
    await click_visibly(app_page, app_page.locator("#settings button[type='submit']"))
    await slow(500)
    await app_page.wait_for_load_state("networkidle")
    print("   Settings saved")
    await slow(1500)

    # ── 10. Recipe upload form ────────────────────────────────────────────────
    print("→ Click 'Add recipe'")
    async with app_page.expect_navigation(timeout=NAV_TIMEOUT):
        await click_visibly(app_page, app_page.locator("a.add-recipe-btn"))
    await app_page.wait_for_load_state("networkidle")
    await slow(1000)

    print("→ Recipe upload form: cake.jpg")
    # Park the cursor on the Add button early so it's visibly there through
    # the whole form-fill, not just a blink right before the click.
    await hover_visibly(app_page, app_page.locator("#create-btn"))
    await app_page.set_input_files("input[name='file']", CAKE_IMG)
    await slow(700)
    await app_page.fill("input#recipe_title", RECIPE_TITLE)
    await slow(700)
    await app_page.fill("textarea#recipe_text", RECIPE_TEXT)
    await slow(1500)
    await click_visibly(app_page, app_page.locator("#create-btn"))
    await app_page.wait_for_url(f"{BASE_URL}/admin", timeout=UPLOAD_TIMEOUT)
    print("   Recipe submitted, task enqueued")
    await slow(1000)

    # ── 11. Flower: task just created ────────────────────────────────────────
    print("→ Flower: task created")
    await switch_to(flower_page)
    got_task = await wait_flower_new_task(flower_before_snapshot, timeout=20.0, poll=2.0)
    print(f"   New task visible in Flower: {got_task}")
    await slow(2500)

    # ── 12. Search with the same image: not indexed yet ──────────────────────
    print("→ Image search: cake.jpg (before task completes)")
    await switch_to(app_page)
    await app_page.goto(BASE_URL, timeout=NAV_TIMEOUT)
    await app_page.wait_for_load_state("networkidle")
    await slow(1000)
    await app_page.set_input_files("input[type='file']", CAKE_IMG)
    await slow(1000)
    await click_visibly(app_page, app_page.locator("#search_btn"))
    await wait_for_search()
    await slow(1000)
    print(f"   {await results.count()} result(s) — not uploaded yet")
    await slow(2000)

    # ── 13. Flower: wait for the task to complete ─────────────────────────────
    print("→ Flower: waiting for task to complete")
    await switch_to(flower_page)
    done = await wait_task_success(TASK_POLL_TIMEOUT, TASK_POLL_INTERVAL)
    print(f"   Task complete: {done}")
    await slow(2000)

    # ── 14. Attu: confirm the record now exists ───────────────────────────────
    print("→ Attu: confirm record for cake.jpg")
    await switch_to(attu_page)
    await attu_query(CAKE_QUERY_EXPR)
    after_text = await attu_table_text()
    print(f"   {after_text[:60]}")
    await slow(2500)

    # ── 15. MinIO: confirm the image file was uploaded ────────────────────────
    print("→ MinIO: confirm cake.jpg was uploaded")
    await switch_to(minio_page)
    await minio_browse_images()
    await minio_filter("cake.jpg")
    found_after = await minio_page.get_by_text("cake.jpg").count() > 0
    print(f"   File visible in MinIO: {found_after}")
    await slow(2500)

    # ── 16. Back to the app: recipe is now indexed ────────────────────────────
    print(f"→ Text search: '{RECIPE_TITLE}' (after task completes)")
    await switch_to(app_page)
    await app_page.goto(BASE_URL, timeout=NAV_TIMEOUT)
    await app_page.wait_for_load_state("networkidle")
    await slow(1000)
    await app_page.fill("input[name='text_query']", RECIPE_TITLE)
    await slow(1000)
    await click_visibly(app_page, app_page.locator("#search_btn"))
    await wait_for_search()
    await slow(1000)
    print(f"   {await results.count()} result(s) — now uploaded")
    await scroll_results()

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
