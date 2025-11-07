from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import os
import re
import time
import json
import shutil
from datetime import datetime

# =========================
# Config (edit these only)
# =========================

GLOBAL_ID = (
    "[GLOBAL_IDENTITY]\n"
    "Scope: Works for any story, genre, or locale; respectful, non-stereotyped depictions.\n"
    "Setting-lock: keep world cues consistent across an image series—geography/landforms, climate/season, architecture, signage/typography, vehicles/gear, materials, ambient sound/lighting cues.\n"
    "Era-lock: preserve implied time period and technology level unless explicitly changed.\n"
    "Palette-lock: maintain a coherent palette and mood for the series (e.g., muted cold blues, warm tungsten interiors).\n"
    "Do-not-change: established setting-lock motifs and layout language; avoid anachronistic skylines or props without instruction.\n"
    "Visual physics: coherent light direction, natural textures, believable scale; no collage or multi-panel layouts.\n"
    "Camera-lock (default): 35mm natural-light look, shallow depth of field, aspect ratio 3:2, subtle film grain. (May be overridden by explicit camera/style requests.)\n"
)

STYLE_WATERCOLOR = (
    "[STYLE_MODULE: watercolor]\n"
    "Transparent washes, visible paper texture, soft edges, pooled pigments at contours, limited palette with indigo/teal accents.\n"
)

STYLE_REALISTIC = (
    "[STYLE_MODULE: realistic]\n"
    "Soft documentary realism, natural muted palette, gentle haze, true-to-life textures, no plastic sheen.\n"
)

STYLE_CARTOON = (
    "[STYLE_MODULE: cartoon]\n"
    "Clean cel-shading, bold outlines, flat color blocks, gentle gradients for sky/water, expressive but not exaggerated faces.\n"
)

CHOSEN_STYLE = STYLE_CARTOON  # or STYLE_REALISTIC / STYLE_CARTOON per run
PROFILE_DIR = r"C:\MyChromeProfile"  # reuse your signed-in Chrome profile
PROMPTS_JSON = "assets/info/story_image_prompts.json"
OUTPUT_DIR = "assets/images"
MAX_PROMPTS = 15
HEADLESS = False  # <--- switch here (True = headless, False = headful)

# =========================
# Helpers
# =========================


def load_prompts(path=PROMPTS_JSON, max_count=MAX_PROMPTS):
    """Load up to max_count prompts from a JSON file under 'image_prompts'."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    prompts = data.get("image_prompts", [])
    return prompts[:max_count]


def build_driver(headless=False, download_dir=None):
    """
    Create a Chrome driver configured to look like a real browser,
    reuse an existing profile, and save downloads to download_dir.
    """
    options = Options()
    options.add_argument(f"user-data-dir={PROFILE_DIR}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")

    # Reduce obvious automation fingerprints
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("detach", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    )
    options.add_argument("--lang=en-US,en;q=0.9")

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

    if download_dir:
        download_dir = os.path.abspath(download_dir)
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)

    drv = webdriver.Chrome(service=Service(), options=options)

    # Stealth tweaks injected before any document loads
    try:
        drv.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            """
            },
        )
    except Exception:
        pass

    # Allow downloads (works in headless/new-headless)
    for domain in ("Browser", "Page"):
        try:
            drv.execute_cdp_cmd(
                f"{domain}.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": download_dir},
            )
            break
        except Exception:
            pass

    return drv


def wait_ready(drv, timeout=30):
    """Wait for document.readyState == 'complete'."""
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def is_interstitial(drv):
    """
    Detect common anti-bot interstitials (e.g., 'Just a moment...').
    Headless often hits these.
    """
    try:
        title = (drv.title or "").lower()
        if "just a moment" in title:
            return True
        html = (drv.page_source or "").lower()
        return ("checking your browser" in html) or ("verifying you are human" in html)
    except Exception:
        return False


def wait_past_interstitial(drv, max_wait=45):
    """Wait for interstitials to clear; refresh once if needed."""
    deadline = time.time() + max_wait
    refreshed = False
    while time.time() < deadline:
        if not is_interstitial(drv):
            return True
        time.sleep(1.0)
        if not refreshed and (deadline - time.time()) < max_wait - 5:
            try:
                drv.refresh()
                wait_ready(drv, timeout=20)
            except Exception:
                pass
            refreshed = True
    return not is_interstitial(drv)


def focus_and_type_prosemirror(drv, text, timeout=25):
    """
    Focus the ChatGPT editor reliably (scroll + click + focus) then type and submit.
    Falls back to a generic ProseMirror selector in headless if the id differs.
    """
    wait = WebDriverWait(drv, timeout)
    editor = None

    # Try the specific id first
    try:
        editor = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "div.ProseMirror#prompt-textarea")
            )
        )
    except Exception:
        # Fallback for headless/variant DOMs
        editor = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "div.ProseMirror[contenteditable='true']")
            )
        )

    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", editor)
    ActionChains(drv).move_to_element(editor).click().pause(0.2).perform()
    drv.execute_script("arguments[0].focus();", editor)
    try:
        editor.send_keys(text)
    except Exception:
        # Some editors swallow send_keys sporadically — pressing Enter still triggers submit.
        pass
    ActionChains(drv).send_keys(Keys.ENTER).perform()


def allow_downloads_to(drv, download_dir):
    """Secondary nudge for download dir (some builds ignore Page.* on first try)."""
    try:
        drv.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )
    except Exception:
        pass


def find_download_button_if_ready(drv):
    """
    Return the download button from the most recent 'Image created' block if visible,
    else None. Uses JS for speed and resilience.
    """
    return drv.execute_script(
        """
        const isVisible = el => el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
        const blocks = [...document.querySelectorAll('div')].filter(
          el => isVisible(el) && /\\bImage created\\b/i.test(el.textContent || '')
        );
        if (!blocks.length) return null;
        const block = blocks.at(-1);
        block.scrollIntoView({block:'center'});
        const btnInBlock = block.querySelector('button[aria-label="Download this image"]');
        const btnAny     = document.querySelector('button[aria-label="Download this image"]');
        return btnInBlock || btnAny || null;
        """
    )


def click_js(drv, element):
    """Click via JS; fall back to dispatching a synthetic click event."""
    try:
        drv.execute_script("arguments[0].click()", element)
    except Exception:
        drv.execute_script(
            """
            const b = arguments[0];
            b.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
            """,
            element,
        )


def wait_for_new_download(dst_dir, before_set, timeout=180):
    """
    Wait until a new non-.crdownload file appears and its size stops changing.
    Return its absolute path, else None on timeout.
    """
    end = time.time() + timeout
    last_path, last_size, stable_ticks = None, None, 0

    while time.time() < end:
        names = set(os.listdir(dst_dir))
        new_files = [
            n for n in names - before_set if not n.lower().endswith(".crdownload")
        ]

        if new_files:
            path = max(
                (os.path.join(dst_dir, n) for n in new_files),
                key=lambda p: os.path.getmtime(p),
            )
            size = os.path.getsize(path)

            if path == last_path and size == last_size:
                stable_ticks += 1
            else:
                stable_ticks, last_path, last_size = 0, path, size

            if stable_ticks >= 4:  # ~2s stable (0.5s * 4)
                return path
        time.sleep(0.5)
    return None


def slugify(text, maxlen=64):
    """Turn arbitrary text into a filename-safe slug."""
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    return (text[:maxlen] or "image").strip("-")


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def list_images(dirpath):
    """Return absolute paths of finished image files in dirpath."""
    return [
        os.path.join(dirpath, f)
        for f in os.listdir(dirpath)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
        and not f.lower().endswith(".crdownload")
    ]


def ensure_sequential_names(dirpath, expected_n, pad_width):
    """
    Final cleanup: ensure files are exactly 01..NN.ext.
    - Keep any file already named with a number (fix padding).
    - Assign remaining files by earliest mtime.
    - Remove extras beyond expected_n.
    """
    imgs = list_images(dirpath)
    if not imgs:
        return

    tmp_records = []  # (tmp_path, ext, mtime, orig_number or None)
    numeric_re = re.compile(r"^(\d+)\.[^.]+$", re.IGNORECASE)

    for p in imgs:
        folder, fname = os.path.split(p)
        base, ext = os.path.splitext(fname)
        number = None
        m = numeric_re.match(fname)
        if m:
            try:
                number = int(m.group(1))
            except Exception:
                number = None
        tmp = os.path.join(folder, fname + ".tmp_move")
        os.replace(p, tmp)
        tmp_records.append((tmp, (ext or ".png"), os.path.getmtime(tmp), number))

    remaining = [r for r in tmp_records]
    for i in range(1, expected_n + 1):
        exact = [r for r in remaining if r[3] == i]
        chosen = exact[0] if exact else None
        if not chosen:
            non_numeric = [r for r in remaining if r[3] is None]
            pool = non_numeric if non_numeric else remaining
            pool.sort(key=lambda r: r[2])  # earliest first
            chosen = pool[0]
        remaining.remove(chosen)

        tmp, ext, _, _ = chosen
        num = f"{i:0{pad_width}d}"
        target = os.path.join(dirpath, f"{num}{ext}")
        try:
            if os.path.exists(target):
                os.remove(target)
        except Exception:
            pass
        os.replace(tmp, target)

    # Remove leftovers if more files than expected_n
    for tmp, _, _, _ in remaining:
        try:
            os.remove(tmp)
        except Exception:
            pass


# =========================
# Main
# =========================


def get_images(headless=False):
    prompts = load_prompts(max_count=MAX_PROMPTS)
    if not prompts:
        raise RuntimeError(f"No prompts found in {PROMPTS_JSON}")

    expected_n = len(prompts)
    pad_width = max(2, len(str(expected_n)))  # 01.. or 001.. depending on count

    root_dir = os.path.abspath(OUTPUT_DIR)
    if os.path.exists(root_dir):
        shutil.rmtree(root_dir)
    os.makedirs(root_dir, exist_ok=True)

    driver = None
    try:
        driver = build_driver(headless=headless, download_dir=root_dir)
        allow_downloads_to(driver, root_dir)

        tabs = []
        orig_handle = None

        for i, prompt in enumerate(prompts):
            if i == 0:
                # Use the initial tab for the first prompt
                orig_handle = driver.current_window_handle
                handle = orig_handle
                driver.switch_to.window(handle)
            else:
                # Open a new tab per prompt
                driver.switch_to.new_window("tab")
                handle = driver.current_window_handle

            driver.get("https://chatgpt.com/")
            wait_ready(driver)

            # Headless often lands on a 'Just a moment...' interstitial
            if is_interstitial(driver):
                ok = wait_past_interstitial(driver, max_wait=45)
                if not ok:
                    # One more try
                    driver.refresh()
                    wait_ready(driver)

            # Type and submit the prompt

            msg = (
                (
                    GLOBAL_ID
                    + CHOSEN_STYLE
                    + " [SCENE] "
                    + prompt
                    + " [OUTPUT] High resolution, aspect ratio 3:2, single-frame composition, no collage."
                )
                .replace("\r", " ")
                .replace("\n", " ")
                .strip()
            )

            # msg = f'Please create an image based on the following prompt: "{prompt}"'
            focus_and_type_prosemirror(driver, msg)

            tabs.append(
                {
                    "handle": handle,
                    "prompt": prompt,
                    "slug": slugify(prompt),
                    "index": i,
                    "state": "waiting_button",  # waiting_button -> downloading -> done
                    "before_set": None,
                    "clicked_at": None,
                    "final_path": None,
                }
            )

        # Poll all tabs until we finish or hit a global time cap
        overall_deadline = time.time() + 60 * 30  # 30 minutes
        stable_ticks, last_seen = 0, None

        while time.time() < overall_deadline:
            # Global early-exit: stop when we already have N images and the set is stable
            current = sorted(list_images(root_dir))
            if len(current) >= expected_n:
                if current == last_seen:
                    stable_ticks += 1
                    if stable_ticks >= 3:  # ~2s settle
                        break
                else:
                    stable_ticks = 0
                    last_seen = current

            remaining = [t for t in tabs if t["state"] != "done"]
            if not remaining:
                break

            for t in remaining:
                driver.switch_to.window(t["handle"])

                if t["state"] == "waiting_button":
                    btn = find_download_button_if_ready(driver)
                    if btn:
                        t["before_set"] = set(os.listdir(root_dir))
                        click_js(driver, btn)
                        t["state"] = "downloading"
                        t["clicked_at"] = time.time()

                elif t["state"] == "downloading":
                    # Give downloads enough time in headless
                    final_path = wait_for_new_download(
                        root_dir, t["before_set"], timeout=200
                    )
                    if final_path:
                        # Rename to sequential name (keeps real extension)
                        ext = os.path.splitext(final_path)[1] or ".png"
                        if not ext.startswith("."):
                            ext = f".{ext}"
                        num = f"{t['index'] + 1:0{pad_width}d}"
                        target_path = os.path.join(root_dir, f"{num}{ext.lower()}")

                        try:
                            if os.path.exists(target_path):
                                os.remove(target_path)  # keep exact 01..NN
                        except Exception:
                            pass

                        # Replace (atomic move on same volume)
                        os.replace(final_path, target_path)
                        t["final_path"] = target_path
                        t["state"] = "done"
                    else:
                        # Per-tab timeout after click (10 min)
                        if time.time() - (t["clicked_at"] or 0) > 600:
                            t["state"] = "done"

            time.sleep(0.6)

        # Final pass: normalize names to exactly 01..NN.ext
        # ensure_sequential_names(root_dir, expected_n, pad_width)

    finally:
        if driver is not None:
            driver.quit()
