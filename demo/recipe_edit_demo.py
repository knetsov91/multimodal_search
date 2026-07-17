"""
Playwright demo: editing a recipe as admin, with Attu (Milvus data browser)
used to verify the underlying record before and after the change.
Covers: admin login, search, edit recipe text, save — cross-checked against
Milvus directly in Attu before and after the edit.
Runs the app and Attu in separate browser tabs, switching between them, so
neither loses its state (search results, query box) while the other is used.
Runs fullscreen (no OS bar) via --start-fullscreen flag.
Saves the session as recipe_edit_demo.gif using async screenshot capture.
"""
import asyncio
import io
import re
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image

ROOT_DIR = Path(__file__).parent.parent
BASE_URL = "http://localhost:8081"
ATTU_URL = "http://localhost:8001/#/databases/default/cooking_3000/data"
FLOWER_URL = "http://localhost:5555/tasks"
GIF_OUT  = ROOT_DIR / "assets" / "recipe_edit_demo.gif"
CAKE_IMG = str(ROOT_DIR / "cake.jpg")

RECIPE_TITLE = "Rainbow Layer Cake"
QUERY_EXPR   = 'img_name == "cake.jpg"'
NEW_TEXT     = "A rainbow layer cake with tangy cream cheese frosting, fresh raspberries, and a dusting of powdered sugar between each layer."
NEW_TEXT_NEEDLE = "fresh raspberries"

SEARCH_TIMEOUT = 30_000
NAV_TIMEOUT    = 10_000
ACTION_TIMEOUT = 15_000
CAPTURE_FPS    = 5
GIF_WIDTH      = 1280
GIF_HEIGHT     = 720
ATTU_POLL_TIMEOUT  = 30.0
ATTU_POLL_INTERVAL = 3.0

# Playwright's synthetic mouse events don't render an OS cursor, so clicks
# otherwise look like the page just teleports into its new state — this
# draws a fake cursor dot that follows real mousemove events.
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

    async def search_image(image_path: str):
        # Image search, not text search: editing the recipe's text changes its
        # text embedding (and can drop it out of a title/text query's top
        # results), but the image embedding is untouched by a text-only edit,
        # so searching by the same image file reliably finds the same recipe.
        await app_page.goto(BASE_URL, timeout=NAV_TIMEOUT)
        await app_page.wait_for_load_state("networkidle")
        await slow(800)
        await app_page.set_input_files("input[type='file']", image_path)
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

    async def wait_attu_contains(expression: str, needle: str, timeout: float, poll: float) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await attu_query(expression)
            if needle in await attu_table_text():
                return True
            await asyncio.sleep(poll)
        return False

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
        # actually differs from the pre-edit snapshot.
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await flower_page.reload(timeout=NAV_TIMEOUT)
            await flower_page.wait_for_load_state("networkidle")
            snap = await flower_snapshot()
            if snap and snap != prev_snapshot:
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

    # ── 2. Flower (separate tab): no task for this edit yet ──────────────────
    print("→ Flower: task list before edit")
    await switch_to(flower_page)
    await flower_show_tasks()
    flower_before_snapshot = await flower_snapshot()
    await slow(2000)
    await switch_to(app_page)

    # ── 3. Search for the cake ───────────────────────────────────────────────
    print(f"→ Search: '{RECIPE_TITLE}'")
    await search_image(CAKE_IMG)
    original_text = await recipe_card().locator("p").inner_text()
    print(f"   Found, text: {original_text[:60]}…")
    await slow(2000)

    # ── 4. Attu (separate tab): show the record before editing ──────────────
    print("→ Attu: record before edit")
    await attu_connect()
    await switch_to(attu_page)
    await attu_query(QUERY_EXPR)
    before_text = await attu_table_text()
    print(f"   {before_text[:80]}")
    await slow(2500)

    # ── 5. Back to the app: edit the recipe text ─────────────────────────────
    print("→ Edit recipe: change text")
    await switch_to(app_page)
    async with app_page.expect_navigation(timeout=NAV_TIMEOUT):
        await click_visibly(app_page, recipe_card().locator("a:has-text('Edit')"))
    await app_page.wait_for_load_state("networkidle")
    await slow(1200)
    await app_page.fill("textarea#recipe_text", NEW_TEXT)
    await slow(1200)
    await app_page.click("#create-btn")
    await app_page.wait_for_url(f"{BASE_URL}/admin", timeout=ACTION_TIMEOUT)
    print("   Edit submitted, task enqueued")
    await slow(1000)

    # ── 6. Flower: the edit task now shows up ─────────────────────────────────
    print("→ Flower: task created")
    await switch_to(flower_page)
    got_task = await wait_flower_new_task(flower_before_snapshot, timeout=20.0, poll=2.0)
    print(f"   New task visible in Flower: {got_task}")
    await slow(2500)

    # ── 7. Attu: wait for the edit task to land, show updated record ────────
    print("→ Attu: waiting for edited text to land")
    await switch_to(attu_page)
    done = await wait_attu_contains(QUERY_EXPR, NEW_TEXT_NEEDLE, ATTU_POLL_TIMEOUT, ATTU_POLL_INTERVAL)
    print(f"   Updated in Milvus: {done}")
    await slow(2500)

    # ── 8. Back to the app: updated text shows in search ─────────────────────
    print(f"→ Search again: '{RECIPE_TITLE}' (verify updated text)")
    await switch_to(app_page)
    await search_image(CAKE_IMG)
    updated_text = await recipe_card().locator("p").inner_text()
    print(f"   Text now: {updated_text[:60]}…")
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
