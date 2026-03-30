import pyodbc
import hashlib
from datetime import datetime

server = 'DESKTOP-EOO77GM\SQLEXPRESS'
database = "TicTacToeDB"

conn_str = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"Trusted_Connection=yes;"
)

def get_conn():
    return pyodbc.connect(conn_str)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_user(email, password):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Id, PasswordHash, Banned, PhotoPath FROM [Users] WHERE [Email]=?", email)
        row = cursor.fetchone()
        if not row:
            return None
        user_id, db_hash, banned, photo = row
        if banned:
            return "BANNED"
        if db_hash == hash_password(password):
            return {"Id": user_id, "Email": email, "Photo": photo}
        return None

def register_user(email, password):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Id FROM [Users] WHERE [Email]=?", email)
        if cursor.fetchone():
            return False
        cursor.execute("INSERT INTO [Users] ([Email], [PasswordHash]) VALUES (?, ?)", email, hash_password(password))
        conn.commit()
        return True

def update_photo(user_id, path):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE [Users] SET [PhotoPath]=? WHERE Id=?", path, user_id)
        conn.commit()

def get_all_users():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT [Email], [PasswordHash], [Banned] FROM [Users]")
        return cursor.fetchall()

def ban_user(email):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE [Users] SET [Banned]=1 WHERE [Email]=?", email)
        conn.commit()

def delete_user(email):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM [Users] WHERE [Email]=?", email)
        conn.commit()

def create_game(player1_id, player2_id):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO [Games] (Player1Id, Player2Id, CreatedAt) VALUES (?, ?, ?)",
            player1_id, player2_id, datetime.now()
        )
        conn.commit()
        return cursor.execute("SELECT @@IDENTITY").fetchone()[0]

def add_move(game_id, player_id, row, col, symbol):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO [Moves] (GameId, PlayerId, Row, Col, Symbol, CreatedAt) VALUES (?, ?, ?, ?, ?, ?)",
            game_id, player_id, row, col, symbol, datetime.now()
        )
        conn.commit()