from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
import time, os

# ✅ Your existing Chrome profile (must already be logged into ChatGPT)
profile_path = r"C:\MyChromeProfile"

options = Options()
options.add_argument(f"user-data-dir={profile_path}")
# options.add_argument("profile-directory=Profile 1")  # ← only if you actually use a sub-profile
options.add_argument("--start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

service = Service()  # chromedriver from PATH / Selenium Manager
driver = webdriver.Chrome(service=service, options=options)

def wait_ready(drv, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

def focus_and_type_prosemirror(drv, text, timeout=25):
    wait = WebDriverWait(drv, timeout)
    # Your DOM shows: <div contenteditable="true" class="ProseMirror" id="prompt-textarea">
    sel = (By.CSS_SELECTOR, "div.ProseMirror#prompt-textarea")
    editor = wait.until(EC.visibility_of_element_located(sel))

    # Make sure it's in view and focused
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", editor)
    ActionChains(drv).move_to_element(editor).click().pause(0.2).perform()
    drv.execute_script("arguments[0].focus();", editor)

    # Try regular typing first
    try:
        editor.send_keys(text)
    except Exception:
        pass

    # If still empty, inject text via ProseMirror-friendly events
    current_text = drv.execute_script("return arguments[0].innerText", editor) or ""
    if not current_text.strip():
        drv.execute_script("""
            const el = arguments[0];
            const txt = arguments[1];
            el.focus();
            // Place caret at start
            const sel = window.getSelection();
            sel.removeAllRanges();
            const r = document.createRange();
            r.selectNodeContents(el);
            r.collapse(true);
            sel.addRange(r);
            // Tell editors text is being inserted
            el.dispatchEvent(new InputEvent('beforeinput', {inputType:'insertText', data:txt, bubbles:true, composed:true}));
            // Try the legacy path first (many editors still hook this)
            try { document.execCommand('insertText', false, txt); } catch (e) {}
            // Also fire an 'input' event for frameworks that listen there
            el.dispatchEvent(new InputEvent('input', {inputType:'insertText', data:txt, bubbles:true, composed:true}));
        """, editor, text)

    # Send the message (Enter)
    ActionChains(drv).send_keys(Keys.ENTER).perform()

try:
    driver.get("https://chatgpt.com/")  # avoid the www redirect variant
    wait_ready(driver)
    time.sleep(1)

    # Defensive: close common popups if they appear
    for label in ("New chat", "Use ChatGPT", "Okay", "Accept", "Got it"):
        try:
            btn = WebDriverWait(driver, 1.5).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[normalize-space()='{label}']"))
            )
            btn.click()
            time.sleep(0.2)
        except TimeoutException:
            pass

    # Type and send
    msg = "Hello from Selenium"
    focus_and_type_prosemirror(driver, msg)

    # Quick confirmation & screenshot
    time.sleep(5)
    shot = os.path.join(os.getcwd(), "chatgpt_auto_message.png")
    driver.save_screenshot(shot)
    print("Screenshot saved:", shot)

finally:
    try:
        driver.quit()
    except Exception:
        pass
