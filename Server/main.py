import socket
import threading
import json
import os

HOST = "127.0.0.1"
PORT = 5001

sessions = []
lock = threading.Lock()
USERS_FILE = "users.json"

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
        if all(board[i][j] == sym for j in range(3)): return True
        if all(board[j][i] == sym for j in range(3)): return True
    if board[0][0] == board[1][1] == board[2][2] == sym: return True
    if board[0][2] == board[1][1] == board[2][0] == sym: return True
    return False

def board_full(board):
    return all(cell != " " for row in board for cell in row)

def send_board(session):
    state = ",".join(cell for row in session.board for cell in row)
    for p in session.players:
        try:
            p.sendall(f"BOARD {state}\n".encode())
        except:
            pass

def recv_all(conn, size):
    data = b""
    while len(data) < size:
        packet = conn.recv(size - len(data))
        if not packet:
            return None
        data += packet
    return data

def handle_auth(conn):
    buffer = ""
    current_user = None

    while True:
        try:
            data = conn.recv(1024).decode()
        except:
            return None
        if not data:
            return None

        buffer += data
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            parts = line.split()
            if not parts:
                continue

            if parts[0] == "REGISTER":
                email, password = parts[1], parts[2]
                if email in users:
                    conn.sendall("ERROR User exists\n".encode())
                else:
                    users[email] = {"password": password, "photo": ""}
                    save_users(users)
                    conn.sendall("OK\n".encode())

            elif parts[0] == "LOGIN":
                email, password = parts[1], parts[2]
                if email in users and users[email]["password"] == password:
                    current_user = email
                    conn.sendall("SUCCESS\n".encode())
                else:
                    conn.sendall("ERROR Login failed\n".encode())

            elif parts[0] == "PHOTO":
                if current_user:
                    try:
                        size = int(parts[1])
                        data_bytes = recv_all(conn, size)
                        if not data_bytes:
                            return None

                        os.makedirs("avatars", exist_ok=True)
                        filepath = f"avatars/{current_user}.jpg"
                        with open(filepath, "wb") as f:
                            f.write(data_bytes)

                        users[current_user]["photo"] = filepath
                        save_users(users)
                        conn.sendall("PHOTO_OK\n".encode())
                        return current_user
                    except:
                        conn.sendall("ERROR Photo failed\n".encode())

def handle_player(session, conn, pid):
    try:
        conn.sendall(f"SYMBOL {session.symbols[pid]}\n".encode())
    except:
        conn.close()
        return

    buffer = ""
    try:
        while session.game_running:
            try:
                data = conn.recv(1024).decode()
            except:
                break
            if not data:
                break

            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                parts = line.split()
                if len(parts) != 3 or parts[0] != "MOVE":
                    continue

                _, r, c = parts
                try:
                    r = int(r)
                    c = int(c)
                except:
                    continue
                if r not in range(3) or c not in range(3):
                    continue

                if pid == session.current_player and session.board[r][c] == " ":
                    session.board[r][c] = session.symbols[pid]
                    send_board(session)

                    if check_winner(session.board, session.symbols[pid]):
                        for p in session.players:
                            try: p.sendall(f"WIN {session.symbols[pid]}\n".encode())
                            except: pass
                        session.game_running = False
                        break

                    if board_full(session.board):
                        for p in session.players:
                            try: p.sendall("DRAW\n".encode())
                            except: pass
                        session.game_running = False
                        break

                    session.current_player = 1 - session.current_player
    finally:
        conn.close()

def get_session():
    with lock:
        for session in sessions:
            if len(session.players) < 2:
                return session
        new_session = GameSession()
        sessions.append(new_session)
        return new_session

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
            conn.sendall("WAIT\n".encode())
        elif len(session.players) == 2:
            for p in session.players:
                p.sendall("START\n".encode())

        threading.Thread(
            target=handle_player,
            args=(session, conn, pid),
            daemon=True
        ).start()

if __name__ == "__main__":
    start_server()