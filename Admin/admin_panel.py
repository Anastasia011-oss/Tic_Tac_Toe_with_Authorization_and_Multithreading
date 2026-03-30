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

# Подключаемся к серверу
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

# Логинимся как админ (указан в сервере)
send("LOGIN admin admin123")

# GUI
root = tk.Tk()
root.title("Admin Panel")

output = tk.Text(root, width=70, height=15)
output.pack()

users_listbox = tk.Listbox(root, width=50)
users_listbox.pack(pady=5)

selected_user = tk.StringVar()

entry = tk.Entry(root)
entry.pack(pady=5)

# Кнопки
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

def get_sessions():
    output.delete("1.0", tk.END)
    send("GET_SESSIONS")

tk.Button(root, text="Обновить пользователей", command=get_users).pack(pady=5)
tk.Button(root, text="Активные игры", command=get_sessions).pack(pady=5)
tk.Button(root, text="Удалить пользователя", command=delete_user).pack(pady=5)
tk.Button(root, text="Забанить выбранного", command=ban_user).pack(pady=5)

# Поток для получения данных от сервера
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

            elif line == "OK":
                output.insert(tk.END, "OK\n")

            elif line.startswith("ERROR"):
                output.insert(tk.END, line + "\n")

threading.Thread(target=receive, daemon=True).start()

root.mainloop()