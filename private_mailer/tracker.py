from flask import Flask, request, jsonify
import pandas as pd
import sqlite3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import time
import os

app = Flask(__name__)
DB_PATH = r'c:\projects\private_mailer\mailer.db'

# --- 🛰️ ENTERPRISE SMTP GATEWAY CREDENTIALS ---
SMTP_SERVER = "sandbox.smtp.mailtrap.io"
SMTP_PORT = 2525
SMTP_USER = "65f6ef2d13ec33"
SMTP_PASSWORD = "a61809310e7edd" # <-- Keep your working password string here!

def init_enterprise_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Table 1: Stores active API client keys for security authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_clients (
            client_id TEXT PRIMARY KEY,
            secret_key TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    # Table 2: Production outgoing transmission log ledger
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outbound_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT,
            recipient_email TEXT,
            subject TEXT,
            status TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Inject a seed mock corporate token for our test
    cursor.execute("INSERT OR IGNORE INTO api_clients (client_id, secret_key) VALUES ('nepal_wallet_01', 'key_secret_777')")
    conn.commit()
    conn.close()

# --- THE B2B PROGRAMMATIC API GATEWAY ENDPOINT ---
@app.route('/api/v1/send', methods=['POST'])
def handle_api_send_request():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Missing JSON payload packet"}), 400
        
    client_id = data.get("client_id")
    secret_key = data.get("secret_key")
    recipient = data.get("email")
    customer_name = data.get("name")
    voucher_token = data.get("code")

    # 1. B2B Security Authentication Check
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    client = cursor.execute("SELECT * FROM api_clients WHERE client_id=? AND secret_key=? AND status='active'", (client_id, secret_key)).fetchone()
    
    if not client:
        conn.close()
        return jsonify({"status": "error", "message": "Unauthorized API credentials"}), 401

    # 2. Fire Transmission Pipeline Over the SMTP Grid
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)

        msg = MIMEMultipart('alternative')
        msg['From'] = '"Nepal Infrastructure Node" <noreply@nepalenterprise.com>'
        msg['To'] = recipient
        msg['Subject'] = f"Transaction Verified: Welcome {customer_name}!"

        html = f"<html><body><h2>Namaste {customer_name},</h2><p>Your business verification token is: <b>{voucher_token}</b></p></body></html>"
        msg.attach(MIMEText(html, 'html'))

        server.sendmail(msg['From'], recipient, msg.as_string())
        server.quit()

        # 3. Log Success State permanently to SQL Ledger
        cursor.execute("INSERT INTO outbound_ledger (client_id, recipient_email, subject, status) VALUES (?, ?, ?, 'sent')", 
                       (client_id, recipient, msg['Subject']))
        conn.commit()
        conn.close()

        print(f"🚀 SUCCESS: API Dispatched Transactional payload to: {recipient}")
        return jsonify({"status": "success", "message": f"Transactional email queued and sent to {recipient}"}), 200

    except Exception as e:
        # Log Failure State to SQL Ledger if network drops
        cursor.execute("INSERT INTO outbound_ledger (client_id, recipient_email, subject, status) VALUES (?, ?, ?, 'failed')", 
                       (client_id, recipient, f"Failed: Welcome {customer_name}!"))
        conn.commit()
        conn.close()
        print(f"💥 PIPELINE ERROR: {e}")
        return jsonify({"status": "error", "message": f"SMTP Relay infrastructure timeout: {e}"}), 500

if __name__ == '__main__':
    init_enterprise_db()
    print("Enterprise API Mail Gateway Online. Listening on port 8080...")
    app.run(host='127.0.0.1', port=8080, debug=True)
