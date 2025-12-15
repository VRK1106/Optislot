import sqlite3

DB_NAME = "parking.db"

def migrate():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # Check if column exists
            c.execute("PRAGMA table_info(slots)")
            columns = [info[1] for info in c.fetchall()]
            
            if 'is_verified' not in columns:
                print("Adding 'is_verified' column to slots table...")
                c.execute("ALTER TABLE slots ADD COLUMN is_verified INTEGER DEFAULT 0")
                conn.commit()
                print("Migration successful: Column added.")
            else:
                print("Column 'is_verified' already exists.")
                
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
