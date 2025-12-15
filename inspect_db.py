import sqlite3

DB_NAME = "parking.db"

def inspect_slots():
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM slots WHERE slot_id = 'M001'")
        slots = c.fetchall()
        
        print(f"{'Slot ID':<10} | {'Status':<10} | {'Reg Num':<15} | {'Verified':<10}")
        print("-" * 55)
        
        for slot in slots:
            reg = slot['reg_num']
            reg_repr = repr(reg) if reg is not None else "None"
            print(f"{slot['slot_id']:<10} | {slot['status']:<10} | {reg_repr:<15} | {slot['is_verified']:<10}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_slots()
