import socket
import tkinter as tk
from tkinter import ttk
from cryptography.fernet import Fernet
import config
import threading

HOST = config.HOST
PORT = config.PORT

cipher = Fernet(config.FERNET_KEY)

def encrypt(msg):
    return cipher.encrypt(msg.encode())

def decrypt(data):
    try:
        return cipher.decrypt(data).decode()
    except:
        return ""

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((HOST, PORT))

def send(msg):
    data = encrypt(msg)
    length = len(data).to_bytes(4, "big")
    client.sendall(length + data)

def recv():
    length_bytes = client.recv(4)
    if not length_bytes:
        return None

    length = int.from_bytes(length_bytes, "big")
    data = b""
    while len(data) < length:
        packet = client.recv(length - len(data))
        if not packet:
            return None
        data += packet

    return decrypt(data)

send("LOGIN admin admin123")

root = tk.Tk()
root.title("Admin Panel")
root.geometry("650x700")
root.configure(bg="#eaf6ff")

# ===================== USERS TABLE =====================
columns = ("Email", "Photo", "Status")
users_table = ttk.Treeview(root, columns=columns, show="headings", height=8)

for col in columns:
    users_table.heading(col, text=col)
    users_table.column(col, anchor="center", width=200)

users_table.pack(pady=10)

# ===================== BUTTONS =====================
btn_frame = tk.Frame(root, bg="#eaf6ff")
btn_frame.pack(pady=5)

def get_users():
    send("GET_USERS")

def delete_user():
    selected = users_table.focus()
    if not selected:
        return
    email = users_table.item(selected)["values"][0]
    send(f"DELETE_USER {email}")

def ban_user():
    selected = users_table.focus()
    if not selected:
        return
    email = users_table.item(selected)["values"][0]
    send(f"BAN_USER {email}")

def unban_user():
    selected = users_table.focus()
    if not selected:
        return
    email = users_table.item(selected)["values"][0]
    send(f"UNBAN_USER {email}")

def get_history():
    selected = users_table.focus()
    if not selected:
        return
    email = users_table.item(selected)["values"][0]
    send(f"GET_FULL_HISTORY_BY_EMAIL {email}")

tk.Button(btn_frame, text="Refresh", command=get_users, bg="#2ecc71", fg="white", width=10).grid(row=0, column=0, padx=5)
tk.Button(btn_frame, text="BAN", command=ban_user, bg="#9b59b6", fg="white", width=10).grid(row=0, column=1, padx=5)
tk.Button(btn_frame, text="UNBAN", command=unban_user, bg="#8e44ad", fg="white", width=10).grid(row=0, column=2, padx=5)
tk.Button(btn_frame, text="Delete", command=delete_user, bg="#e74c3c", fg="white", width=10).grid(row=0, column=3, padx=5)
tk.Button(btn_frame, text="History", command=get_history, bg="#f39c12", width=10).grid(row=0, column=4, padx=5)

tk.Label(root, text="Match History", bg="#2980b9", fg="white").pack()

history_columns = ("Date", "Players", "Result")
history_table = ttk.Treeview(root, columns=history_columns, show="headings", height=6)

for col in history_columns:
    history_table.heading(col, text=col)
    history_table.column(col, anchor="center", width=200)

history_table.pack(fill="both", padx=10, pady=5)

tk.Label(root, text="Moves (Selected Game)", bg="#3498db", fg="white").pack()

moves_columns = ("Time", "Player", "X", "Y")
moves_table = ttk.Treeview(root, columns=moves_columns, show="headings", height=6)

for col in moves_columns:
    moves_table.heading(col, text=col)
    moves_table.column(col, anchor="center", width=150)

moves_table.pack(fill="both", padx=10, pady=5)

def show_full_history(data):
    for row in history_table.get_children():
        history_table.delete(row)

    if "#" not in data:
        return

    games_part, bans_part = data.split("#", 1)

    if games_part:
        for g in games_part.split(";"):
            if not g:
                continue

            parts = g.split("|")
            if len(parts) < 4:
                continue  # пропускаем некорректные записи
            date, p1, p2, win_id = parts[:4]

            if win_id == "None":
                result = "Draw"
            elif win_id == p1:
                result = f"{p1} won"
            else:
                result = f"{p2} won"

            history_table.insert("", "end",
                                 values=(date, f"{p1} vs {p2}", result),
                                 tags=(g,))

def show_moves(data):
    for row in moves_table.get_children():
        moves_table.delete(row)

    moves = data.split(";")

    for m in moves:
        if not m:
            continue

        parts = m.split("|")
        if len(parts) < 4:
            continue
        time, player, x, y = parts[:4]
        moves_table.insert("", "end", values=(time, player, x, y))

def on_game_select(event):
    selected = history_table.focus()
    if not selected:
        return

    game_data = history_table.item(selected)["tags"][0]
    parts = game_data.split("|")

    game_id = parts[0]

    send(f"GET_MOVES_BY_GAME {game_id}")

history_table.bind("<<TreeviewSelect>>", on_game_select)

def receive():
    while True:
        msg = recv()
        if not msg:
            continue

        for line in msg.split("\n"):

            if line.startswith("USERS"):
                users = line.replace("USERS ", "").split(",")

                for row in users_table.get_children():
                    users_table.delete(row)

                for u in users:
                    parts = u.split("|")
                    if len(parts) == 3:
                        email = parts[0]
                        photo = parts[1]
                        banned = parts[2]

                        photo_status = "OK" if photo not in ("0", "None", "", "False") else "NO"
                        status = "BANNED" if banned == "1" else "ACTIVE"

                        users_table.insert("", "end", values=(email, photo_status, status))

            elif line.startswith("FULL_HISTORY"):
                data = line.split(" ", 1)[1]
                root.after(0, show_full_history, data)

            elif line.startswith("MOVES"):
                data = line.split(" ", 1)[1]
                root.after(0, show_moves, data)

            elif line == "OK":
                print("OK")

            elif line.startswith("ERROR"):
                print(line)

threading.Thread(target=receive, daemon=True).start()

root.mainloop()