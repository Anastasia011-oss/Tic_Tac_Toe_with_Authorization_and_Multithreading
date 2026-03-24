import socket
import threading
import json
import os
import hashlib
import base64
from config import *

sessions = []
lock = threading.Lock()

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

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

users = load_users()

class GameSession:
    def __init__(self):
        self.board = [[" "] * 3 for _ in range(3)]
        self.players = []
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

def handle_auth(conn):
    current_user = None

    while True:
        data = recv(conn)
        if not data:
            return None

        for line in data.split("\n"):
            parts = line.split()
            if not parts:
                continue

            if parts[0] == "REGISTER":
                email, password = parts[1], parts[2]

                if email in users:
                    send(conn, "ERROR User exists")
                else:
                    users[email] = {
                        "password": hash_password(password),
                        "photo": ""
                    }
                    save_users(users)
                    send(conn, "OK")

            elif parts[0] == "LOGIN":
                email, password = parts[1], parts[2]

                if email in users and users[email]["password"] == hash_password(password):
                    current_user = email
                    send(conn, "SUCCESS")
                else:
                    send(conn, "ERROR Login failed")

            elif parts[0] == "PHOTO":
                if current_user:
                    try:
                        encoded = parts[1]
                        data_bytes = base64.b64decode(encoded)

                        os.makedirs(AVATAR_DIR, exist_ok=True)
                        path = f"{AVATAR_DIR}/{current_user}.jpg"

                        with open(path, "wb") as f:
                            f.write(data_bytes)

                        users[current_user]["photo"] = path
                        save_users(users)

                        send(conn, "PHOTO_OK")
                        return current_user
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
            if len(parts) != 3 or parts[0] != "MOVE":
                continue

            r, c = int(parts[1]), int(parts[2])

            if r not in range(3) or c not in range(3):
                continue

            if pid == session.current_player and session.board[r][c] == " ":
                session.board[r][c] = session.symbols[pid]
                send_board(session)

                if check_winner(session.board, session.symbols[pid]):
                    for p in session.players:
                        send(p, f"WIN {session.symbols[pid]}")
                    session.game_running = False
                    break

                if board_full(session.board):
                    for p in session.players:
                        send(p, "DRAW")
                    session.game_running = False
                    break

                session.current_player = 1 - session.current_player

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
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()

    print("Server started...")

    while True:
        conn, addr = server.accept()
        print("Connected:", addr)

        user = handle_auth(conn)
        if not user:
            conn.close()
            continue

        session = get_session()
        pid = len(session.players)
        session.players.append(conn)

        if len(session.players) == 1:
            send(conn, "WAIT")
        else:
            for p in session.players:
                send(p, "START")

        threading.Thread(
            target=handle_player,
            args=(session, conn, pid),
            daemon=True
        ).start()

if __name__ == "__main__":
    start_server()