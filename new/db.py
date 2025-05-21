import sqlite3
from datetime import datetime
import time

class Database:
    def __init__(self, db_name='bot.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                phone TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS times (
                time TEXT PRIMARY KEY
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                user_id INTEGER,
                time TEXT,
                status TEXT
                time TEXT,  -- Masalan: '2025-05-16 16:00'
                name TEXT,
                surname TEXT,
                phone TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS advertisement_status (
                id INTEGER PRIMARY KEY,
                status TEXT
        )""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS location (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        

    def set_advertisement_sent(self):
        self.cursor.execute("REPLACE INTO advertisement_status (id, status) VALUES (1, 'sent')")
        self.conn.commit()

    # E'lon yuborilganini tekshirish
    def is_advertisement_sent(self):
        self.cursor.execute("SELECT status FROM advertisement_status WHERE id = 1")
        result = self.cursor.fetchone()
        return result and result[0] == 'sent'

    def execute_sql_with_time(self, query, params=None):
        start_time = time.time()
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        self.conn.commit()
        execution_time = time.time() - start_time
        return execution_time, self.cursor.fetchall()


    def add_user(self, user_id, phone):
        self.cursor.execute("INSERT OR IGNORE INTO users (id, phone) VALUES (?, ?)", (user_id, phone))
        self.conn.commit()

    def is_registered(self, user_id):
        self.cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_user_phone(self, user_id):
        self.cursor.execute("SELECT phone FROM users WHERE id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def add_admin(self, user_id):
        self.cursor.execute("INSERT OR IGNORE INTO admins (id) VALUES (?)", (user_id,))
        self.conn.commit()

    def is_admin(self, user_id):
        self.cursor.execute("SELECT 1 FROM admins WHERE id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_all_admins(self):
        self.cursor.execute("SELECT id FROM admins")
        return self.cursor.fetchall()

    def add_time(self, time_str):
        # time_str format: "15:30"
        today_date = datetime.now().strftime("%Y-%m-%d")
        full_time = f"{today_date} {time_str}"
        self.cursor.execute("INSERT OR IGNORE INTO times (time) VALUES (?)", (full_time,))
        self.conn.commit()

    def delete_time(self, time):
        self.cursor.execute("DELETE FROM times WHERE time = ?", (time,))
        self.conn.commit()

    def get_all_times(self):
        self.cursor.execute("SELECT time FROM times")
        return [t[0] for t in self.cursor.fetchall()]

    def get_free_times(self):
        self.cursor.execute("""
            SELECT t.time FROM times t
            LEFT JOIN bookings b ON t.time = b.time
            WHERE b.time IS NULL
        """)
        return [row[0] for row in self.cursor.fetchall()]

    def is_time_booked(self, time):
        self.cursor.execute("SELECT 1 FROM bookings WHERE time = ?", (time,))
        return self.cursor.fetchone() is not None

    def book_time(self, user_id, time):
        self.cursor.execute("INSERT INTO bookings (user_id, time, status) VALUES (?, ?, ?)", (user_id, time, 'pending'))
        self.conn.commit()

    def cancel_booking(self, time):
        self.cursor.execute("DELETE FROM bookings WHERE time = ?", (time,))
        self.conn.commit()

    def get_user_bookings(self, user_id):
        self.cursor.execute("SELECT time, status FROM bookings WHERE user_id = ?", (user_id,))
        return self.cursor.fetchall()

    def get_all_bookings(self):
        self.cursor.execute("SELECT user_id, time, status FROM bookings")
        return self.cursor.fetchall()

    def accept_booking(self, user_id, time):
        self.cursor.execute("UPDATE bookings SET status = 'accepted' WHERE user_id = ? AND time = ?", (user_id, time))
        self.conn.commit()

    def reject_booking(self, user_id, time):
        self.cursor.execute("DELETE FROM bookings WHERE user_id = ? AND time = ?", (user_id, time))
        self.conn.commit()

    def has_booking_today(self, user_id):
        today = datetime.now().date().isoformat()
        self.cursor.execute("""
            SELECT 1 FROM bookings
            WHERE user_id = ? AND DATE(time) = ?
        """, (user_id, today))
        return self.cursor.fetchone() is not None

    def get_all_users(self):
        self.cursor.execute("SELECT id FROM users")
        return self.cursor.fetchall()
    
        # Lokatsiya jadvalini yaratish (agar mavjud bo'lmasa)
    def init_db():
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS location (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()


    # Lokatsiyani bazaga saqlash
    def save_location(latitude, longitude):
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO location (latitude, longitude) VALUES (?, ?)", (latitude, longitude))
        conn.commit()
        conn.close()


    # Eng oxirgi lokatsiyani olish
    def get_latest_location():
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT latitude, longitude FROM location ORDER BY created_at DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        return result
    
