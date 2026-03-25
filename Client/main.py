import socket
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
from cryptography.fernet import Fernet
import base64
import config

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

symbol = ""
buttons = []
root = tk.Tk()
root.withdraw()
current_window = None
avatar_photo = None

def choose_action():
    global current_window
    if current_window:
        current_window.destroy()

    win = tk.Toplevel()
    current_window = win
    win.title("Выбор")

    tk.Label(win, text="Выберите действие", font=("Arial", 12)).pack(pady=10)
    tk.Button(win, text="Войти", width=20, command=lambda: open_auth(win, "LOGIN")).pack(pady=5)
    tk.Button(win, text="Регистрация", width=20, command=lambda: open_auth(win, "REGISTER")).pack(pady=5)

def open_auth(prev_window, mode):
    global current_window
    prev_window.destroy()

    win = tk.Toplevel()
    current_window = win
    win.title("Вход" if mode=="LOGIN" else "Регистрация")

    tk.Label(win, text="Email").pack()
    email_entry = tk.Entry(win)
    email_entry.pack()

    tk.Label(win, text="Пароль").pack()
    pass_entry = tk.Entry(win, show="*")
    pass_entry.pack()

    def submit():
        send(f"{mode} {email_entry.get()} {pass_entry.get()}")

    tk.Button(win, text="Отправить", command=submit).pack(pady=10)
    tk.Button(win, text="Назад", command=choose_action).pack(pady=5)

def choose_photo():
    global avatar_photo

    path = filedialog.askopenfilename()
    if not path:
        messagebox.showerror("Ошибка", "Выберите фото обязательно!")
        return

    with open(path, "rb") as f:
        data = f.read()

    encoded = base64.b64encode(data).decode()
    send(f"PHOTO {encoded}")

    img = Image.open(path)
    img = img.resize((60, 60))
    avatar_photo = ImageTk.PhotoImage(img)

def build_game_ui():
    global current_window, status_label, frame

    if current_window:
        current_window.destroy()

    root.deiconify()
    root.title("Tic Tac Toe")

    top_frame = tk.Frame(root)
    top_frame.pack(side="top", fill="x", pady=10)

    if avatar_photo:
        avatar_label = tk.Label(top_frame, image=avatar_photo)
        avatar_label.image = avatar_photo
        avatar_label.pack(side="left", padx=10)

    status_label = tk.Label(top_frame, text="")
    status_label.pack(side="left", padx=10)

    frame = tk.Frame(root)
    frame.pack(side="top", pady=20)

    for r in range(3):
        row = []
        for c in range(3):
            btn = tk.Button(frame, text=" ", width=10, height=4,
                            command=lambda r=r, c=c: click(r, c))
            btn.grid(row=r, column=c)
            row.append(btn)
        buttons.append(row)

def click(r, c):
    try:
        send(f"MOVE {r} {c}")
    except:
        pass

def update_board(state):
    cells = state.split(",")
    for i in range(9):
        r = i // 3
        c = i % 3
        buttons[r][c]["text"] = cells[i]

def receive():
    global symbol

    while True:
        try:
            msg = recv()
            if not msg:
                continue
        except:
            break

        for line in msg.split("\n"):
            if not line:
                continue

            if line.startswith("ERROR"):
                root.after(0, lambda: messagebox.showerror("Ошибка", line))

            elif line == "OK":
                root.after(0, lambda: messagebox.showinfo("Успех", "Регистрация успешна"))

            elif line == "SUCCESS":
                root.after(0, choose_photo)

            elif line == "PHOTO_OK":
                root.after(0, build_game_ui)

            elif line == "WAIT":
                root.after(0, lambda: status_label.config(text="Waiting for opponent..."))

            elif line == "START":
                root.after(0, lambda: status_label.config(text="Game started"))

            elif line.startswith("SYMBOL"):
                symbol = line.split()[1]
                root.after(0, lambda: root.title(f"You are {symbol}"))

            elif line.startswith("BOARD"):
                state = line.split(" ", 1)[1]
                root.after(0, update_board, state)

            elif line.startswith("WIN"):
                root.after(0, lambda: messagebox.showinfo("Game", "Win"))

            elif line == "DRAW":
                root.after(0, lambda: messagebox.showinfo("Game", "Draw"))

threading.Thread(target=receive, daemon=True).start()

def on_close():
    try:
        client.shutdown(socket.SHUT_RDWR)
        client.close()
    except:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

choose_action()
root.mainloop()
threading.Thread(target=receive, daemon=True).start()

def on_close():
    try:
        client.shutdown(socket.SHUT_RDWR)
        client.close()
    except:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

choose_action()
root.mainloop()