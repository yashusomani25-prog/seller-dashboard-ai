import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import time #

CSV_PATH = r"c:\projects\private_mailer\subscribers.csv"

# --- SERVER SETTINGS ---
SMTP_SERVER = "sandbox.smtp.mailtrap.io"
SMTP_PORT = 2525
SMTP_USER = "65f6ef2d13ec33"
SMTP_PASSWORD = "a61809310e7edd"  # <-- Paste your password string here

def run_smtp_pipeline():
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"Error reading subscribers.csv: {e}")
        return

    try:
        print("Connecting to remote SMTP network relay...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        print("✓ SMTP Authentication Successful!")

        for index, row in df.iterrows():
            email_recipient = row["email"]
            name = row["first_name"]
            code = row["discount_code"]

            msg = MIMEMultipart("alternative")
            msg["From"] = '"Nepal Tech Enterprise" <noreply@nepalenterprise.com>'
            msg["To"] = email_recipient
            msg["Subject"] = f"Namaste {name}, exclusive access inside!"

            html_content = f"""
            <html>
              <body>
                <h2>Namaste {name},</h2>
                <p>Your custom system access token is: <b>{code}</b></p>
              </body>
            </html>
            """
            msg.attach(MIMEText(html_content, "html"))

            server.sendmail(msg["From"], email_recipient, msg.as_string())
            print(f"  Email package transmitted cleanly to: {email_recipient}")
            time.sleep(11) #
 
        server.quit()
        print("\n✓ All email packages dispatched over the network loop!")

    except Exception as e:
        print(f"💥 Network pipeline failed. Error details: {e}")

if __name__ == "__main__":
    run_smtp_pipeline()
