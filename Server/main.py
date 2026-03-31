import socket
import threading
import json
import os
import hashlib
import base64
import pyodbc
import time
from config import *

sessions = []
lock = threading.Lock()

conn_str = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"Trusted_Connection=yes;"
)

def get_conn():
    return pyodbc.connect(conn_str)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def encrypt(msg):
    return fernet.encrypt(msg.encode())

def decrypt(data):
    try:
        return fernet.decrypt(data).decode()
    except:
        return ""

def send(conn, msg):
    try:
        data = encrypt(msg)
        length = len(data).to_bytes(4, "big")
        conn.sendall(length + data)
    except:
        pass

def recv(conn):
    try:
        length_bytes = conn.recv(4)
        if not length_bytes:
            return None
        length = int.from_bytes(length_bytes, "big")
        data = b""
        while len(data) < length:
            packet = conn.recv(length - len(data))
            if not packet:
                return None
            data += packet
        return decrypt(data)
    except:
        return None


def save_game(player1, player2, winner):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO GameHistory (Player1Id, Player2Id, WinnerId) VALUES (?, ?, ?)",
            player1, player2, winner
        )
        conn.commit()

def get_user_full_history(user_id):
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT GameDate, Player1Id, Player2Id, WinnerId
            FROM GameHistory
            WHERE Player1Id=? OR Player2Id=?
            ORDER BY GameDate DESC
        """, user_id, user_id)
        games = cursor.fetchall()

        cursor.execute("""
            SELECT BanDate, UnbanDate
            FROM BanHistory
            WHERE UserId=?
            ORDER BY BanDate DESC
        """, user_id)
        bans = cursor.fetchall()

        return games, bans


def get_all_users():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Email, PasswordHash, Banned FROM [Users]")
        return cursor.fetchall()

def ban_user(email):
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT Id FROM Users WHERE Email=?", email)
        user_id = cursor.fetchone()[0]

        cursor.execute("UPDATE [Users] SET [Banned]=1 WHERE [Email]=?", email)

        cursor.execute(
            "INSERT INTO BanHistory (UserId) VALUES (?)",
            user_id
        )

        conn.commit()

def unban_user(email):
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT Id FROM Users WHERE Email=?", email)
        user_id = cursor.fetchone()[0]

        cursor.execute("UPDATE [Users] SET [Banned]=0 WHERE [Email]=?", email)

        cursor.execute("""
            UPDATE BanHistory
            SET UnbanDate = GETDATE()
            WHERE UserId=? AND UnbanDate IS NULL
        """, user_id)

        conn.commit()

def delete_user(email):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM [Users] WHERE [Email]=?", email)
        conn.commit()


class GameSession:
    def __init__(self):
        self.board = [[" "] * 3 for _ in range(3)]
        self.players = []
        self.player_ids = []
        self.symbols = ["X", "O"]
        self.current_player = 0
        self.game_running = True

def check_winner(board, sym):
    for i in range(3):
        if all(board[i][j] == sym for j in range(3)):
            return True
        if all(board[j][i] == sym for j in range(3)):
            return True
    if board[0][0] == board[1][1] == board[2][2] == sym:
        return True
    if board[0][2] == board[1][1] == board[2][0] == sym:
        return True
    return False

def board_full(board):
    return all(cell != " " for row in board for cell in row)

def send_board(session):
    state = ",".join(cell for row in session.board for cell in row)
    for p in session.players:
        send(p, f"BOARD {state}")


def check_user(email, password):
    if email == "admin" and password == "admin123":
        return {"Id": -1}

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Id, PasswordHash, Banned FROM [Users] WHERE [Email]=?", email)
        row = cursor.fetchone()
        if not row:
            return None

        user_id, db_hash, banned = row

        if banned:
            return "BANNED"

        if db_hash == hash_password(password):
            return {"Id": user_id}

        return None

def register_user(email, password):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Id FROM [Users] WHERE [Email]=?", email)
        if cursor.fetchone():
            return False

        cursor.execute(
            "INSERT INTO [Users] ([Email], [PasswordHash], [Banned], [PhotoPath]) VALUES (?, ?, 0, '')",
            email, hash_password(password)
        )
        conn.commit()
        return True

def update_photo(email, path):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE [Users] SET [PhotoPath]=? WHERE [Email]=?", path, email)
        conn.commit()


def handle_admin(conn):
    while True:
        data = recv(conn)
        if not data:
            break

        for line in data.split("\n"):
            parts = line.split()
            if not parts:
                continue

            cmd = parts[0]

            if cmd == "GET_USERS":
                users = get_all_users()
                result = []
                for u in users:
                    email, pwd, banned = u
                    result.append(f"{email}|{pwd}|{int(banned)}")

                send(conn, "USERS " + ",".join(result))

            elif cmd == "BAN_USER":
                if len(parts) > 1:
                    ban_user(parts[1])
                    send(conn, "OK")

            elif cmd == "UNBAN_USER":
                if len(parts) > 1:
                    unban_user(parts[1])
                    send(conn, "OK")

            elif cmd == "DELETE_USER":
                if len(parts) > 1:
                    delete_user(parts[1])
                    send(conn, "OK")

            elif cmd == "GET_SESSIONS":
                with lock:
                    active = len([s for s in sessions if len(s.players) > 0])
                send(conn, f"SESSIONS Active games: {active}")

            elif cmd == "GET_FULL_HISTORY":
                if len(parts) < 2:
                    send(conn, "ERROR Invalid command")
                    continue

                try:
                    uid = int(parts[1])
                except:
                    send(conn, "ERROR Invalid ID")
                    continue

                games, bans = get_user_full_history(uid)

                game_data = []
                for g in games:
                    date, p1, p2, win = g
                    game_data.append(f"{date}|{p1}|{p2}|{win}")

                ban_data = []
                for b in bans:
                    ban_date, unban_date = b
                    ban_data.append(f"{ban_date}|{unban_date}")

                send(conn, "FULL_HISTORY " +
                     ";".join(game_data) + "#" +
                     ";".join(ban_data))

            elif cmd == "GET_FULL_HISTORY_BY_EMAIL":
                if len(parts) < 2:
                    send(conn, "ERROR No email")
                    continue

                email = parts[1]

                try:
                    with get_conn() as db:
                        cursor = db.cursor()
                        cursor.execute("SELECT Id FROM Users WHERE Email=?", email)
                        row = cursor.fetchone()

                        if not row:
                            send(conn, "ERROR User not found")
                            continue

                        uid = row[0]

                except Exception as e:
                    print("DB ERROR:", e)
                    send(conn, "ERROR DB failure")
                    continue

                games, bans = get_user_full_history(uid)

                game_data = []
                for g in games:
                    date, p1, p2, win = g
                    game_data.append(f"{date}|{p1}|{p2}|{win}")

                ban_data = []
                for b in bans:
                    ban_date, unban_date = b
                    ban_data.append(f"{ban_date}|{unban_date}")

                send(conn, "FULL_HISTORY " +
                     ";".join(game_data) + "#" +
                     ";".join(ban_data))

def handle_auth(conn):
    current_user = None
    current_user_id = None

    while True:
        data = recv(conn)
        if not data:
            return None

        for line in data.split("\n"):
            parts = line.split()
            if not parts:
                continue

            cmd = parts[0]

            if cmd == "REGISTER":
                if register_user(parts[1], parts[2]):
                    send(conn, "OK")
                else:
                    send(conn, "ERROR User exists")

            elif cmd == "LOGIN":
                status = check_user(parts[1], parts[2])

                if status == "BANNED":
                    send(conn, "ERROR BANNED")

                elif status:
                    current_user = parts[1]
                    current_user_id = status["Id"]
                    send(conn, "SUCCESS")

                    if current_user_id == -1:
                        handle_admin(conn)
                        return -1
                else:
                    send(conn, "ERROR Login failed")

            elif cmd == "PHOTO":
                if current_user and current_user_id != -1:
                    try:
                        data_bytes = base64.b64decode(parts[1])
                        os.makedirs(AVATAR_DIR, exist_ok=True)
                        path = f"{AVATAR_DIR}/{current_user}.jpg"
                        with open(path, "wb") as f:
                            f.write(data_bytes)
                        update_photo(current_user, path)
                        send(conn, "PHOTO_OK")
                        # не return
                    except:
                        send(conn, "ERROR Photo failed")


def handle_player(session, conn, pid):
    send(conn, f"SYMBOL {session.symbols[pid]}")

    while session.game_running:
        data = recv(conn)
        if not data:
            break

        for line in data.split("\n"):
            parts = line.split()
            if len(parts) != 3:
                continue

            r, c = int(parts[1]), int(parts[2])

            if pid != session.current_player:
                continue

            if session.board[r][c] != " ":
                continue

            session.board[r][c] = session.symbols[pid]

            if check_winner(session.board, session.symbols[pid]):
                send_board(session)

                winner_id = session.player_ids[pid]
                save_game(session.player_ids[0], session.player_ids[1], winner_id)

                for p in session.players:
                    send(p, f"WIN {session.symbols[pid]}")

                session.game_running = False
                break

            if board_full(session.board):
                send_board(session)

                save_game(session.player_ids[0], session.player_ids[1], None)

                for p in session.players:
                    send(p, "DRAW")

                session.game_running = False
                break

            session.current_player = 1 - session.current_player
            send_board(session)

    conn.close()

def get_session():
    with lock:
        for s in sessions:
            if len(s.players) < 2:
                return s
        s = GameSession()
        sessions.append(s)
        return s


def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen()

    print("Server started...")

    while True:
        conn, addr = server_socket.accept()
        print("Connected:", addr)

        user_id = handle_auth(conn)

        if user_id == -1:
            continue

        if not user_id:
            conn.close()
            continue

        session = get_session()

        with lock:
            pid = len(session.players)
            session.players.append(conn)
            session.player_ids.append(user_id)

        if len(session.players) == 1:
            send(conn, "WAIT")

        elif len(session.players) == 2:
            for p in session.players:
                send(p, "START")

            time.sleep(0.1)
            send_board(session)

        threading.Thread(
            target=handle_player,
            args=(session, conn, pid),
            daemon=True
        ).start()

if __name__ == "__main__":
    start_server()