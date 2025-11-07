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
from datetime import datetime
import argparse  # CHANGE: CLI flags for headless on/off
import shutil  # add this at the top of your file


# ---------- Helpers ----------


# This will load promopts and maximum of 6 prompts.
def load_prompts(path="assets/info/story_image_prompts.json", max_count=6):
    with open(path, "r") as f:
        data = json.load(f)
    prompts = data.get("image_prompts", [])
    return prompts[:max_count]


# --- build_driver: add a download_dir argument and prefs ---


# this is setting the browser settings, like user profile, where to download files etc...
def build_driver(headless=False, download_dir=None):  # CHANGE
    options = Options()
    options.add_argument(r"user-data-dir=C:\MyChromeProfile")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("detach", False)
    if headless:
        options.add_argument("--headless=new")

    # Force Chrome to use our download directory
    if download_dir:  # CHANGE
        download_dir = os.path.abspath(download_dir)
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)

    service = Service()
    drv = webdriver.Chrome(service=service, options=options)

    # Strongly nudge via CDP (Browser first, then Page)  # CHANGE
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


# function will wait until the document is ready and the timeout it 30 sec. meaning it will wait for maximum 30 secound.
def wait_ready(drv, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def focus_and_type_prosemirror(drv, text, timeout=25):
    # This is waiting for driver to be ready
    wait = WebDriverWait(drv, timeout)

    # this is selecting the input (chatgpt input)
    sel = (By.CSS_SELECTOR, "div.ProseMirror#prompt-textarea")
    # this is checking if the sel is visible or not
    editor = wait.until(EC.visibility_of_element_located(sel))

    # this is like editor[0].scrollIntoview({block: 'center'}), this will block the scroolview
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", editor)

    # this will move to the element and then click on the input field and then do editor[0].focus();
    ActionChains(drv).move_to_element(editor).click().pause(0.2).perform()
    drv.execute_script("arguments[0].focus();", editor)
    try:
        # this will send the keys meaning this will paste the message in the text editor
        editor.send_keys(text)
    except Exception:
        pass

    # This will press enter so that the messages goes
    ActionChains(drv).send_keys(Keys.ENTER).perform()


def allow_downloads_to(drv, download_dir):
    # Fallback (some Chrome versions ignore Page.* outside headless)
    # this is a fallback so that the it should download only on our specified locaiton
    try:
        drv.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )
    except Exception:
        pass


# This is going to find the download button and if found it's going to return that button
def find_download_button_if_ready(drv):
    # Returns a WebElement when the newest “Image created” block has a download button
    return drv.execute_script(
        """
        const isVisible = el => el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
        const blocks = [...document.querySelectorAll('div')].filter(
          el => isVisible(el) && /\\bImage created\\b/i.test(el.textContent || '')
        );
        if (!blocks.length) return null;
        const block = blocks.at(-1); //This is going to find the last most element which contain text "Image created"
        block.scrollIntoView({block:'center'});
        const btnInBlock = block.querySelector('button[aria-label="Download this image"]');
        const btnAny     = document.querySelector('button[aria-label="Download this image"]');
        return btnInBlock || btnAny || null;
        """
    )


# This will click on the given element.
def click_js(drv, element):
    try:
        #  this is similar to element[0].click() in puppettier
        drv.execute_script("arguments[0].click()", element)
    except Exception:
        # if the previous method fails this will work as fallback
        drv.execute_script(
            """
            const b = arguments[0];
            b.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
            """,
            element,
        )


def wait_for_new_download(dst_dir, before_set, timeout=180):

    end = time.time() + timeout
    last_path, last_size, stable_ticks = None, None, 0

    while time.time() < end:

        # Checks if there's any new files int he des_dir without (.crdownload)

        # this list all the images in the dst_dir
        names = set(os.listdir(dst_dir))

        # this get all new downloaded images (before set = previous image set.)
        new_files = [
            n for n in names - before_set if not n.lower().endswith(".crdownload")
        ]

        # If there's a new file, and also check if the size if stable meaning downloading compleated. if compleated it's going to return path.
        if new_files:

            # this is for getting the last images path
            path = max(
                (os.path.join(dst_dir, n) for n in new_files),
                key=lambda p: os.path.getmtime(p),
            )

            size = os.path.getsize(path)

            # This check if files size is increasing or not if increasing that means file is downloading.
            if path == last_path and size == last_size:
                stable_ticks += 1
            else:
                stable_ticks, last_path, last_size = 0, path, size
            if stable_ticks >= 4:  # ~2s at 0.5s intervals
                # After download compleated we're going to return the file path.
                return path
        time.sleep(0.5)
    return None


# slugify("My Cool File!!") → "my-cool-file"
def slugify(text, maxlen=64):
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    return (text[:maxlen] or "image").strip("-")


# ---------- NEW: image listing & final renamer ----------

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}  # CHANGE


# ["C:/Downloads/pic1.png", "C:/Downloads/photo.jpg", ...] this function return all the images inside the dirpath
def list_images(dirpath):  # CHANGE
    return [
        os.path.join(dirpath, f)
        for f in os.listdir(dirpath)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
        and not f.lower().endswith(".crdownload")
    ]


# This will ensure name like 01.jpg, 02.jpg, 03.jpg etc..
def ensure_sequential_names(dirpath, expected_n, pad_width):  # CHANGE
    """
    Normalize whatever is in dirpath to 01.ext..NN.ext:
    - Preserve existing numeric names (1/01/etc.) but fix zero-padding.
    - Assign remaining files in mtime order to remaining numbers.
    """
    imgs = list_images(dirpath)
    if not imgs:
        return

    # Move to temp names first to avoid collisions
    tmp_records = []  # (tmp_path, ext, mtime, orig_number or None)
    numeric_re = re.compile(r"^(\\d+)\\.[^.]+$", re.IGNORECASE)

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

    # Choose file for each slot 1..expected_n
    used = set()
    remaining = [r for r in tmp_records]
    # Prefer files that already had the right numeric index
    for i in range(1, expected_n + 1):
        # First: exact numeric match
        exact = [r for r in remaining if r[3] == i]
        chosen = exact[0] if exact else None
        if not chosen:
            # Next: any numeric (wrong index) won't be preferred; pick by earliest mtime
            non_numeric = [r for r in remaining if r[3] is None]
            pool = non_numeric if non_numeric else remaining
            pool.sort(key=lambda r: r[2])  # earliest first
            chosen = pool[0]
        remaining.remove(chosen)
        used.add(chosen[0])

        tmp, ext, _, _ = chosen
        num = f"{i:0{pad_width}d}"
        target = os.path.join(dirpath, f"{num}{ext}")
        try:
            if os.path.exists(target):
                os.remove(target)
        except Exception:
            pass
        os.replace(tmp, target)

    # Clean any leftovers (more files than expected_n)
    for tmp, _, _, _ in remaining:
        try:
            os.remove(tmp)
        except Exception:
            pass


# ---------- Main logic ----------


def main(headless=False):

    # This is loading image prompts from json
    prompts = load_prompts(max_count=6)

    if not prompts:
        raise RuntimeError("No prompts found in assets/info/story_image_prompts.json")

    expected_n = len(prompts)  # how many images should we wait for download
    pad_width = max(
        2, len(str(expected_n))
    )  # zero-padding width 01.png / 001.png etc..

    root_dir = os.path.abspath("output_images")
    if os.path.exists(root_dir):
        shutil.rmtree(root_dir)
    os.makedirs(root_dir, exist_ok=True)

    driver = None
    try:
        driver = build_driver(headless=headless, download_dir=root_dir)  # CHANGE
        allow_downloads_to(driver, root_dir)  # CHANGE

        # Track per-tab state
        tabs = []

        # Reuse the already-open initial tab for the first prompt
        orig_handle = driver.current_window_handle

        # This will create new window, but for the first one it will use existing one and then go to chatgpt.com and wait for driver to ready  and sleep for 0.8 s and then using focus_and_type_prosemirror() it will send the message and also it will store some information about the tabs using tabs.append(),
        for i, prompt in enumerate(prompts):

            # this will check if i = 0 and first windows is open or not, if opened it will use that existing window
            if i == 0 and orig_handle in driver.window_handles:
                handle = orig_handle
                driver.switch_to.window(handle)
            else:
                # This will create new tab and go to chatgopt.
                driver.switch_to.new_window("tab")
                handle = driver.current_window_handle

            driver.get("https://chatgpt.com/")
            # This is checking if the webpage is ready or not.
            wait_ready(driver)
            time.sleep(0.8)

            msg = f'Please create an image based on the following prompt: "{prompt}"'
            focus_and_type_prosemirror(driver, msg)

            tabs.append(
                {
                    "handle": handle,  # The browser tab ID (so the script can switch back to it later).
                    "prompt": prompt,  # The text prompt sent to ChatGPT to generate the image.
                    "slug": slugify(
                        prompt
                    ),  # A short, filename-safe version of the prompt (via slugify(prompt) — removes spaces/symbols).
                    "index": i,  # numbering comes from prompt order
                    "state": "waiting_button",  # waiting_button → downloading → done
                    "before_set": None,  # Stores the list of files in the folder before clicking the download button — helps detect the new file later.
                    "clicked_at": None,  # this is used for timeout logic
                    "final_path": None,  # Will later hold the full file path of the downloaded image.
                }
            )

        # Poll each tab until we either finish all, or the folder has N images (stable)
        overall_deadline = time.time() + 60 * 30  # 30 min cap
        stable_ticks, last_seen = 0, None  # CHANGE: global finish by file count

        while time.time() < overall_deadline:
            # Global stop: when we already have N images and the set is stable

            current = sorted(list_images(root_dir))

            if len(current) >= expected_n:
                if current == last_seen:
                    stable_ticks += 1
                    if stable_ticks >= 3:  # ~2 seconds settle
                        break
                else:
                    stable_ticks = 0
                    last_seen = current

            # Remaining means those tabs whose steate is anything but not "done"
            remaining = [t for t in tabs if t["state"] != "done"]

            # if there is no remeaning left meaning everything is "done" then break the while loop
            if not remaining:
                break

            # Here we're going to loop through all remaining tabs.
            for t in remaining:

                # here t["handle"] = remaining["handle"]. remaining = tabs which is not "done";
                driver.switch_to.window(t["handle"])

                if t["state"] == "waiting_button":
                    btn = find_download_button_if_ready(driver)
                    if btn:
                        t["before_set"] = set(os.listdir(root_dir))
                        click_js(driver, btn)
                        t["state"] = "downloading"
                        t["clicked_at"] = time.time()

                elif t["state"] == "downloading":

                    # This will return the final path of the file which has been downloaded compleatly
                    # Increasing the timeout did actually worked!
                    final_path = wait_for_new_download(
                        root_dir, t["before_set"], timeout=200
                    )
                    if final_path:
                        # Rename immediately to index-based name (keeps true extension)
                        ext = os.path.splitext(final_path)[1] or ".png"
                        if not ext.startswith("."):
                            ext = f".{ext}"
                        num = f"{t['index'] + 1:0{pad_width}d}"
                        target_path = os.path.join(root_dir, f"{num}{ext}")

                        try:
                            if os.path.exists(target_path):
                                os.remove(target_path)  # keep exact 01..NN
                        except Exception:
                            pass

                        os.replace(final_path, target_path)
                        t["final_path"] = target_path
                        t["state"] = "done"
                    else:
                        # Per-tab timeout after click (10 min)
                        if time.time() - t["clicked_at"] > 600:
                            t["state"] = "done"

            time.sleep(0.6)

        # Final normalization: ensure we have 01..NN.ext exactly  # CHANGE
        # ensure_sequential_names(root_dir, expected_n, pad_width)

    finally:
        if driver is not None:
            driver.quit()  # CHANGE: always close Chrome when finished


if __name__ == "__main__":
    # CHANGE: CLI switches to toggle headless mode
    parser = argparse.ArgumentParser(description="Generate and download images.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode (no visible window).",
    )
    parser.add_argument(
        "--show",
        dest="headless",
        action="store_false",
        help="Run with a visible Chrome window.",
    )
    parser.set_defaults(headless=False)
    args = parser.parse_args()

    main(headless=args.headless)  # CHANGE
