import pandas as pd
import sqlite3
import os

DB_PATH = r'c:\projects\private_mailer\mailer.db'
CSV_PATH = r'c:\projects\private_mailer\subscribers.csv'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS click_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            target_url TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✓ SQLite Database file initialized successfully.")

def process_campaign_locally():
    if not os.path.exists(CSV_PATH):
        print(f"💥 Error: {CSV_PATH} does not exist. Please check the path.")
        return

    # Read your subscriber list directly using Pandas
    df = pd.read_csv(CSV_PATH)
    
    # Open direct database connection string
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\nProcessing subscribers via Pandas loop...")
    for index, row in df.iterrows():
        email_recipient = row['email']
        name = row['first_name']
        
        # Simulate catching an automated click tracking event
        target_link = "https://google.com"
        
        # Write the tracking metrics directly to the SQLite database
        cursor.execute("INSERT INTO click_logs (email, target_url) VALUES (?, ?)", (email_recipient, target_link))
        print(f" 💾 Direct Save: Logged mock click event for {name} ({email_recipient})")
        
    conn.commit()
    conn.close()
    print("\n✓ Local pipeline complete. Database sync finished!")

if __name__ == '__main__':
    init_db()
    process_campaign_locally()
