from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
import time
import random

def random_sleep(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))

options = Options()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 20)

try:
    print("Opening Instagram login page...")
    driver.get("https://www.instagram.com/accounts/login/")
    random_sleep(5, 8)   # Give page time to fully load

    # === Fill Username ===
    print("Entering email/username...")
    username_input = wait.until(
        EC.presence_of_element_located((By.NAME, "username"))
    )
    username_input.clear()
    username_input.click()
    username_input.send_keys("worldgeniusyash25@gmail.com")
    random_sleep(1.2, 2.5)

    # === Fill Password ===
    print("Entering password...")
    password_input = wait.until(
        EC.presence_of_element_located((By.NAME, "password"))
    )
    password_input.clear()
    password_input.click()
    password_input.send_keys("Y@shusomani25victoryinquantumfield")
    random_sleep(1.5, 3)

    print("Trying to click Log In button...")

    # Multiple attempts with different reliable selectors
    clicked = False
    for attempt in range(4):
        try:
            # Best selectors for current Instagram (2026)
            login_btn = wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR, "button[type='submit']"
            )))
            login_btn.click()
            print(f"✅ Clicked login button (attempt {attempt+1})")
            clicked = True
            break
        except ElementClickInterceptedException:
            print("Click was intercepted, trying JavaScript click...")
            driver.execute_script("arguments[0].click();", login_btn)
            clicked = True
            break
        except:
            random_sleep(2, 4)

    if not clicked:
        print("⚠️ Could not click button. Trying one more backup method...")
        driver.execute_script("""
            document.querySelector("button[type='submit']").click();
        """)

    # Wait after clicking
    random_sleep(8, 15)

    current_url = driver.current_url
    print(f"Current URL: {current_url}")

    if "login" not in current_url.lower() and "accounts" not in current_url.lower():
        print("✅ Login appears successful!")
    else:
        print("❌ Still on login page. Possible reasons:")
        print("   • Instagram detected automation")
        print("   • 2FA / Security check required")
        print("   • 'Save login info?' popup")
        print("   • Temporary block from too many attempts")

except TimeoutException:
    print("⏰ Timeout: Could not find username/password fields.")
    print("   Instagram page structure may have changed again.")
except Exception as e:
    print(f"❌ Error: {e}")

finally:
    print("\nBrowser is kept open so you can see what's happening.")
    print("If you see any popup (Save info? / Not Now / 2FA code), handle it manually.")
    input("\nPress Enter to close the browser when done...")
    driver.quit()