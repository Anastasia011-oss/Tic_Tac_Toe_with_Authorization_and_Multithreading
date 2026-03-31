import socket
import tkinter as tk
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

output = tk.Text(root, width=70, height=15)
output.pack()

users_listbox = tk.Listbox(root, width=50)
users_listbox.pack(pady=5)

selected_user = tk.StringVar()

def get_users():
    users_listbox.delete(0, tk.END)
    send("GET_USERS")

def delete_user():
    email = users_listbox.get(tk.ACTIVE)
    if email:
        send(f"DELETE_USER {email.split(' | ')[0]}")

def ban_user():
    email = users_listbox.get(tk.ACTIVE)
    if email:
        send(f"BAN_USER {email.split(' | ')[0]}")

def unban_user():
    email = users_listbox.get(tk.ACTIVE)
    if email:
        send(f"UNBAN_USER {email.split(' | ')[0]}")

def get_sessions():
    output.delete("1.0", tk.END)
    send("GET_SESSIONS")


def get_history():
    email = users_listbox.get(tk.ACTIVE)
    if not email:
        return

    email = email.split(" | ")[0]

    send(f"GET_FULL_HISTORY_BY_EMAIL {email}")

def show_full_history(data):
    win = tk.Toplevel()
    win.title("История пользователя")

    games_part, bans_part = data.split("#")

    tk.Label(win, text="=== ИГРЫ ===").pack()

    if games_part:
        for g in games_part.split(";"):
            if not g:
                continue

            date, p1, p2, win_id = g.split("|")

            if win_id == "None":
                result = "Ничья"
            elif win_id == p1:
                result = f"Победил: {p1}"
            else:
                result = f"Победил: {p2}"

            text = f"{date} | {p1} vs {p2} | {result}"
            tk.Label(win, text=text).pack()

    tk.Label(win, text="=== БАНЫ ===").pack()

    if bans_part:
        for b in bans_part.split(";"):
            if not b:
                continue

            ban_date, unban_date = b.split("|")

            if unban_date == "None":
                status = "Активен"
            else:
                status = f"Разбан: {unban_date}"

            text = f"Бан: {ban_date} | {status}"
            tk.Label(win, text=text).pack()


tk.Button(root, text="Обновить пользователей", command=get_users).pack(pady=5)
tk.Button(root, text="Активные игры", command=get_sessions).pack(pady=5)
tk.Button(root, text="Удалить пользователя", command=delete_user).pack(pady=5)
tk.Button(root, text="Забанить выбранного", command=ban_user).pack(pady=5)
tk.Button(root, text="Разбанить выбранного", command=unban_user).pack(pady=5)

tk.Button(root, text="История пользователя", command=get_history).pack(pady=5)

def receive():
    while True:
        msg = recv()
        if not msg:
            continue

        for line in msg.split("\n"):

            if line.startswith("USERS"):
                users = line.replace("USERS ", "").split(",")

                users_listbox.delete(0, tk.END)
                output.insert(tk.END, "=== USERS ===\n")

                for u in users:
                    parts = u.split("|")
                    if len(parts) == 3:
                        email = parts[0]
                        banned = parts[2]
                        display = f"{email} | banned={banned}"
                        users_listbox.insert(tk.END, display)
                        output.insert(tk.END, display + "\n")

            elif line.startswith("SESSIONS"):
                output.insert(tk.END, "=== SESSIONS ===\n")
                output.insert(tk.END, line + "\n")

            elif line.startswith("FULL_HISTORY"):
                data = line.split(" ", 1)[1]
                root.after(0, show_full_history, data)

            elif line == "OK":
                output.insert(tk.END, "OK\n")

            elif line.startswith("ERROR"):
                output.insert(tk.END, line + "\n")

threading.Thread(target=receive, daemon=True).start()

root.mainloop()