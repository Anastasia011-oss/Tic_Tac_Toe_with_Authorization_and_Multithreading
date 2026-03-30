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

server = 'DESKTOP-EOO77GM\\SQLEXPRESS'
database = 'TicTacToeDB'

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

class GameSession:
    def __init__(self):
        self.board = [[" "] * 3 for _ in range(3)]
        self.players = []
        self.player_ids = []
        self.symbols = ["X", "O"]
        self.current_player = 0
        self.game_running = True
        self.game_id = None

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
            return {"Id": user_id}
        return None

def register_user(email, password):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Id FROM [Users] WHERE [Email]=?", email)
        if cursor.fetchone():
            return False
        cursor.execute("INSERT INTO [Users] ([Email], [PasswordHash], [Banned], [PhotoPath]) VALUES (?, ?, 0, '')",
                       email, hash_password(password))
        conn.commit()
        return True

def update_photo(email, path):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE [Users] SET [PhotoPath]=? WHERE [Email]=?", path, email)
        conn.commit()

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
                else:
                    send(conn, "ERROR Login failed")

            elif cmd == "PHOTO":
                if current_user:
                    try:
                        data_bytes = base64.b64decode(parts[1])
                        os.makedirs(AVATAR_DIR, exist_ok=True)
                        path = f"{AVATAR_DIR}/{current_user}.jpg"

                        with open(path, "wb") as f:
                            f.write(data_bytes)

                        update_photo(current_user, path)
                        send(conn, "PHOTO_OK")
                        return current_user_id
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
                for p in session.players:
                    send(p, f"WIN {session.symbols[pid]}")
                session.game_running = False
                break

            if board_full(session.board):
                send_board(session)
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