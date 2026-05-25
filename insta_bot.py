from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

options = Options()
options.add_argument(r"--user-data-dir=C:\Users\user\selenium_profile")
options.add_argument("--start-maximized")
options.add_argument("--remote-debugging-port=9222")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

print("Opening Instagram...")
driver.get("https://www.instagram.com/")

wait = WebDriverWait(driver, 15)

# ✅ Handle "Save login info?" popup
try:
    not_now_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Not Now')]")))
    not_now_btn.click()
    print("Clicked Not Now (save login)")
except:
    pass

# ✅ Handle "Turn on notifications" popup
try:
    not_now_btn2 = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Not Now')]")))
    not_now_btn2.click()
    print("Clicked Not Now (notifications)")
except:
    pass

print("Instagram ready.")

# 🔥 KEEP OPEN (important)
input("Browser is open. Press Enter to close...")

driver.quit()