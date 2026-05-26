import sqlite3
import pandas as pd

DB_PATH = r'c:\projects\private_mailer\mailer.db'

def display_dashboard_metrics():
    print("====================================================")
    print("       📊 PRIVATE MAILER CAMPAIGN ANALYTICS        ")
    print("====================================================\n")
    
    # Connect directly to the SQLite database
    conn = sqlite3.connect(DB_PATH)
    
    # Use Pandas to read the SQL table cleanly
    try:
        query = "SELECT * FROM click_logs"
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            print("No tracking data found in database yet.")
        else:
            # Print the total numbers
            print(f"📈 Total Tracked Click Interactions: {len(df)}")
            print("-" * 52)
            # Print the raw dataframe structure beautifully
            print(df.to_string(index=False))
            
    except Exception as e:
        print(f"Error accessing database records: {e}")
    finally:
        conn.close()
    print("\n====================================================")

if __name__ == '__main__':
    display_dashboard_metrics()
