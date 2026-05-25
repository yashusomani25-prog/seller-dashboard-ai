from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

driver = webdriver.Chrome()
driver.maximize_window()

# 1. Start from homepage
driver.get("https://sellercenter.daraz.com.np/")
time.sleep(5)

# 2. Click the Login link
login_link = driver.find_element(By.XPATH, "//a[contains(@href,'login')]")
login_link.click()
print("Clicked Login link...")

# 3. FIX: Check if a new tab opened and switch to it
time.sleep(3)
if len(driver.window_handles) > 1:
    driver.switch_to.window(driver.window_handles[-1])
    print("Switched to the login tab.")

# 4. Wait for the actual login fields (using the text from your screenshot)
wait = WebDriverWait(driver, 20)
try:
    print("Searching for the 'Mobile Number/ Email' box...")
    
    # Target the exact placeholder from your image
    email_field = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//input[contains(@placeholder, 'Mobile Number')]")
    ))
    
    # Focus and Type
    email_field.click()
    email_field.send_keys("worldgeniusyash25@gmail.com")
    print("EMAIL TYPED")

    password_field = driver.find_element(By.XPATH, "//input[@type='password']")
    password_field.send_keys("Y@shusomani25victoryinquantumfield")
    print("PASSWORD TYPED")

    # Click the orange Login button
    login_btn = driver.find_element(By.XPATH, "//button[contains(., 'Login')]")
    login_btn.click()
    print("LOGIN CLICKED")

except Exception as e:
    print(f"Still can't find it. Error: {e}")

input("Check the browser now! Press Enter to close...")
driver.quit()