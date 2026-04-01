import socket
import threading
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


def save_game(p1, p2, winner):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO GameHistory (Player1Id, Player2Id, WinnerId) OUTPUT INSERTED.Id VALUES (?, ?, ?)",
            p1, p2, winner
        )
        game_id = cursor.fetchone()[0]
        conn.commit()
        return game_id


def update_game_winner(game_id, winner):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE GameHistory SET WinnerId=? WHERE Id=?",
            winner, game_id
        )
        conn.commit()


def save_move(game_id, player_id, x, y):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Moves (GameId, PlayerId, X, Y) VALUES (?, ?, ?, ?)",
            game_id, player_id, x, y
        )
        conn.commit()


def get_moves_by_game(game_id):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MoveTime, PlayerId, X, Y
            FROM Moves
            WHERE GameId=?
            ORDER BY MoveTime
        """, game_id)
        return cursor.fetchall()


def update_photo(email, path):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET PhotoPath=? WHERE Email=?", path, email)
        conn.commit()


def get_photo(uid):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT PhotoPath FROM Users WHERE Id=?", uid)
        row = cursor.fetchone()
        return row[0] if row else None


def get_all_users():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Email, PasswordHash, Banned FROM Users")
        return cursor.fetchall()


def ban_user(email):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET Banned=1 WHERE Email=?", email)
        cursor.execute("""
            INSERT INTO BanHistory (UserId, BanDate, UnbanDate)
            SELECT Id, GETDATE(), NULL FROM Users WHERE Email=?
        """, email)
        conn.commit()


def unban_user(email):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET Banned=0 WHERE Email=?", email)
        cursor.execute("""
            UPDATE BanHistory
            SET UnbanDate=GETDATE()
            WHERE UserId=(SELECT Id FROM Users WHERE Email=?)
            AND UnbanDate IS NULL
        """, email)
        conn.commit()


def delete_user(email):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Users WHERE Email=?", email)
        conn.commit()


def get_user_full_history_by_email(email):
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT Id FROM Users WHERE Email=?", email)
        row = cursor.fetchone()
        if not row:
            return [], []

        uid = row[0]

        cursor.execute("""
            SELECT Id, GameDate, Player1Id, Player2Id, WinnerId
            FROM GameHistory
            WHERE Player1Id=? OR Player2Id=?
            ORDER BY GameDate DESC
        """, uid, uid)
        games = cursor.fetchall()

        cursor.execute("""
            SELECT BanDate, UnbanDate
            FROM BanHistory
            WHERE UserId=?
            ORDER BY BanDate DESC
        """, uid)
        bans = cursor.fetchall()

        return games, bans


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
                ban_user(parts[1])
                send(conn, "OK")

            elif cmd == "UNBAN_USER":
                unban_user(parts[1])
                send(conn, "OK")

            elif cmd == "DELETE_USER":
                delete_user(parts[1])
                send(conn, "OK")

            elif cmd == "GET_FULL_HISTORY_BY_EMAIL":
                email = parts[1]

                games, bans = get_user_full_history_by_email(email)

                game_data = []
                for g in games:
                    gid, date, p1, p2, win = g
                    game_data.append(f"{gid}|{date}|{p1}|{p2}|{win}")

                ban_data = []
                for b in bans:
                    ban_date, unban_date = b
                    ban_data.append(f"{ban_date}|{unban_date}")

                send(conn, "FULL_HISTORY " +
                     ";".join(game_data) + "#" +
                     ";".join(ban_data))

            elif cmd == "GET_MOVES_BY_GAME":
                game_id = parts[1]

                moves = get_moves_by_game(game_id)

                result = []
                for m in moves:
                    time, player, x, y = m
                    result.append(f"{time}|{player}|{x}|{y}")

                send(conn, "MOVES " + ";".join(result))



def check_user(email, password):
    if email == "admin" and password == "admin123":
        return {"Id": -1}

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Id, PasswordHash, Banned FROM Users WHERE Email=?", email)
        row = cursor.fetchone()

        if not row:
            return None

        uid, db_hash, banned = row

        if banned:
            return "BANNED"

        if db_hash == hash_password(password):
            return {"Id": uid}

        return None


def register_user(email, password):
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT Id FROM Users WHERE Email=?", email)
        if cursor.fetchone():
            return False

        cursor.execute(
            "INSERT INTO Users (Email, PasswordHash, Banned, PhotoPath) VALUES (?, ?, 0, '')",
            email, hash_password(password)
        )
        conn.commit()
        return True


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

            # ===== LOGIN =====
            if cmd == "LOGIN":
                email = parts[1]
                password = parts[2]

                status = check_user(email, password)

                if status == "BANNED":
                    send(conn, "BANNED")
                    continue

                if status:
                    current_user = email
                    current_user_id = status["Id"]

                    photo = get_photo(current_user_id)

                    if not photo:
                        send(conn, "NEED_PHOTO")
                    else:
                        send(conn, "SUCCESS")
                        return current_user_id

                    if current_user_id == -1:
                        handle_admin(conn)
                        return -1

                else:
                    send(conn, "FAIL")


            # ===== UPLOAD PHOTO =====
            elif cmd == "UPLOAD_PHOTO":
                if not current_user:
                    continue

                try:
                    img_data = base64.b64decode(parts[1])

                    os.makedirs("photos", exist_ok=True)
                    path = f"photos/{current_user}.png"

                    with open(path, "wb") as f:
                        f.write(img_data)

                    update_photo(current_user, path)

                    send(conn, "SUCCESS")

                    return current_user_id

                except Exception as e:
                    print("Photo error:", e)
                    send(conn, "FAIL")

            # ===== REGISTER =====
            elif cmd == "REGISTER":
                email = parts[1]
                password = parts[2]

                if register_user(email, password):
                    send(conn, "REGISTER_SUCCESS")
                else:
                    send(conn, "REGISTER_FAIL")

            # ===== ЗАГРУЗКА ФОТО =====
            elif cmd == "UPLOAD_PHOTO":
                if not current_user:
                    continue

                try:
                    img_data = base64.b64decode(parts[1])

                    os.makedirs("photos", exist_ok=True)
                    path = f"photos/{current_user}.png"

                    with open(path, "wb") as f:
                        f.write(img_data)

                    update_photo(current_user, path)

                    send(conn, "SUCCESS")

                except Exception as e:
                    print("Photo error:", e)
                    send(conn, "FAIL")

            if current_user_id:
                return current_user_id


class GameSession:
    def __init__(self):
        self.board = [[" "] * 3 for _ in range(3)]
        self.players = []
        self.player_ids = []
        self.symbols = ["X", "O"]
        self.current = 0
        self.running = True
        self.game_id = None


def check_winner(b, s):
    for i in range(3):
        if all(b[i][j] == s for j in range(3)):
            return True
        if all(b[j][i] == s for j in range(3)):
            return True

    if b[0][0] == b[1][1] == b[2][2] == s:
        return True
    if b[0][2] == b[1][1] == b[2][0] == s:
        return True

    return False


def board_full(b):
    return all(cell != " " for row in b for cell in row)


def send_board(session):
    state = ",".join(cell for row in session.board for cell in row)
    for p in session.players:
        send(p, f"BOARD {state}")


def handle_player(session, conn, pid):
    send(conn, f"SYMBOL {session.symbols[pid]}")

    while session.running:
        data = recv(conn)
        if not data:
            break

        for line in data.split("\n"):
            parts = line.split()
            if len(parts) != 3:
                continue

            r, c = int(parts[1]), int(parts[2])

            if pid != session.current:
                continue

            if session.board[r][c] != " ":
                continue

            session.board[r][c] = session.symbols[pid]

            save_move(session.game_id, session.player_ids[pid], r, c)

            if check_winner(session.board, session.symbols[pid]):
                send_board(session)

                update_game_winner(session.game_id,
                                   session.player_ids[pid])

                for p in session.players:
                    send(p, f"WIN {session.symbols[pid]}")

                session.running = False
                break

            if board_full(session.board):
                send_board(session)
                update_game_winner(session.game_id, None)

                for p in session.players:
                    send(p, "DRAW")

                session.running = False
                break

            session.current = 1 - session.current
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
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()

    print("Server started...")

    while True:
        conn, addr = server.accept()
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
            # 🔥 создаём игру
            session.game_id = save_game(
                session.player_ids[0],
                session.player_ids[1],
                None
            )

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