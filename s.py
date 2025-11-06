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


# ---------- Helpers ----------


def load_prompts(path="assets/info/story_image_prompts.json", max_count=6):
    with open(path, "r") as f:
        data = json.load(f)
    prompts = data.get("image_prompts", [])
    return prompts[:max_count]


def build_driver():
    options = Options()
    options.add_argument(r"user-data-dir=C:\MyChromeProfile")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("detach", True)
    service = Service()
    return webdriver.Chrome(service=service, options=options)


def wait_ready(drv, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def focus_and_type_prosemirror(drv, text, timeout=25):
    wait = WebDriverWait(drv, timeout)
    sel = (By.CSS_SELECTOR, "div.ProseMirror#prompt-textarea")
    editor = wait.until(EC.visibility_of_element_located(sel))
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", editor)
    ActionChains(drv).move_to_element(editor).click().pause(0.2).perform()
    drv.execute_script("arguments[0].focus();", editor)
    try:
        editor.send_keys(text)
    except Exception:
        pass
    ActionChains(drv).send_keys(Keys.ENTER).perform()


def allow_downloads_to(drv, download_dir):
    try:
        drv.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )
    except Exception:
        pass


def find_download_button_if_ready(drv):
    # Returns a WebElement (button) when the newest “Image created” block is present and has a download button, else None
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
            if stable_ticks >= 4:  # ~2s at 0.5s intervals
                return path
        time.sleep(0.5)
    return None


def slugify(text, maxlen=64):
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    return (text[:maxlen] or "image").strip("-")


# ---------- Main logic ----------


def main():
    prompts = load_prompts(max_count=6)  # indexes 0..5 (or fewer if not available)
    if not prompts:
        raise RuntimeError("No prompts found in assets/info/story_image_prompts.json")

    driver = build_driver()
    download_dir = os.path.abspath("output_images")
    os.makedirs(download_dir, exist_ok=True)
    allow_downloads_to(driver, download_dir)

    # Open a tab per prompt and send the messages
    tabs = []
    for i, prompt in enumerate(prompts):
        driver.switch_to.new_window("tab")
        handle = driver.current_window_handle
        driver.get("https://chatgpt.com/")
        wait_ready(driver)
        time.sleep(0.8)

        msg = f'Please create an image based on the following prompt: "{prompt}"'
        focus_and_type_prosemirror(driver, msg)

        tabs.append(
            {
                "handle": handle,
                "prompt": prompt,
                "slug": slugify(prompt),
                "state": "waiting_button",  # waiting_button -> clicked -> downloading -> done
                "before_set": None,
                "clicked_at": None,
                "final_path": None,
            }
        )

    print(
        f"Submitted {len(tabs)} prompts across {len(tabs)} tabs. Waiting for downloads..."
    )

    # Poll each tab until all have finished or timeout
    overall_deadline = time.time() + 60 * 30  # 30 min hard cap for all
    while time.time() < overall_deadline:
        remaining = [t for t in tabs if t["state"] != "done"]
        if not remaining:
            break

        for t in remaining:
            driver.switch_to.window(t["handle"])

            # 1) Wait for the "Image created" download button and click when ready
            if t["state"] == "waiting_button":
                btn = find_download_button_if_ready(driver)
                if btn:
                    print(f"[{t['slug']}] Image ready — clicking download")
                    t["before_set"] = set(os.listdir(download_dir))
                    click_js(driver, btn)
                    t["state"] = "downloading"
                    t["clicked_at"] = time.time()

            # 2) After click, watch download folder for a new stable file
            elif t["state"] == "downloading":
                final_path = wait_for_new_download(
                    download_dir, t["before_set"], timeout=1
                )
                if final_path:
                    base = f"{t['slug']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    ext = os.path.splitext(final_path)[1] or ".png"
                    target_path = os.path.join(download_dir, base + ext)
                    os.replace(final_path, target_path)
                    t["final_path"] = target_path
                    t["state"] = "done"
                    print(f"[{t['slug']}] Saved: {target_path}")
                else:
                    # Optional per-tab timeout (e.g., 10 min after click)
                    if time.time() - t["clicked_at"] > 600:
                        print(f"[{t['slug']}] Download timeout after click.")
                        t["state"] = "done"

        time.sleep(0.6)

    # Report any unfinished tabs
    unfinished = [t for t in tabs if t["state"] != "done"]
    if unfinished:
        for t in unfinished:
            print(f"[{t['slug']}] did not finish.")
    else:
        print("All downloads completed.")


if __name__ == "__main__":
    main()
