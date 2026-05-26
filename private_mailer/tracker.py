from flask import Flask, request, send_file, redirect
import pandas as pd
import sqlite3
import io

app = Flask(__name__)
DB_PATH = r'c:\projects\private_mailer\mailer.db'

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

@app.route('/')
def home():
    return "<h1>Mail Tracking Server is Active!</h1><p>Use test_click.py to send data.</p>"

@app.route('/track/click', methods=['GET'])
def track_click():
    recipient = request.args.get('email')
    target_url = request.args.get('url')
    
    # Save the tracked click to the database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO click_logs (email, target_url) VALUES (?, ?)", (recipient, target_url))
    conn.commit()
    conn.close()
    
    print(f"\n💾 DATABASE LOGGED SUCCESS: {recipient} click saved to mailer.db!")
    return redirect(target_url if target_url else "https://google.com")

if __name__ == '__main__':
    init_db()
    print("Database Engine Server Online on port 8080...")
    app.run(host='127.0.0.1', port=8080, debug=True)
