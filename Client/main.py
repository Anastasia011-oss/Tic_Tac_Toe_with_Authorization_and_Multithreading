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

# --- ГЛОБАЛЬНЫЕ ---
symbol = ""
current_turn = ""
buttons = []
status_label = None
ui_ready = False
last_state = None

root = tk.Tk()
root.withdraw()
current_window = None
avatar_photo = None

# ---------- UI ----------
def choose_action():
    global current_window
    if current_window:
        current_window.destroy()

    win = tk.Toplevel()
    current_window = win
    win.title("Выбор")

    tk.Button(win, text="Войти", command=lambda: open_auth(win, "LOGIN")).pack()
    tk.Button(win, text="Регистрация", command=lambda: open_auth(win, "REGISTER")).pack()

def open_auth(prev, mode):
    prev.destroy()
    win = tk.Toplevel()

    tk.Label(win, text="Email").pack()
    email = tk.Entry(win)
    email.pack()

    tk.Label(win, text="Пароль").pack()
    pw = tk.Entry(win, show="*")
    pw.pack()

    tk.Button(win, text="OK", command=lambda: send(f"{mode} {email.get()} {pw.get()}")).pack()

def choose_photo():
    global avatar_photo
    path = filedialog.askopenfilename()

    if not path:
        messagebox.showerror("Ошибка", "Выберите фото!")
        return

    with open(path, "rb") as f:
        data = f.read()

    send(f"PHOTO {base64.b64encode(data).decode()}")

    img = Image.open(path).resize((60, 60))
    avatar_photo = ImageTk.PhotoImage(img)

def build_game_ui():
    global status_label, buttons, ui_ready, last_state

    root.deiconify()

    top = tk.Frame(root)
    top.pack()

    if avatar_photo:
        tk.Label(top, image=avatar_photo).pack(side="left")

    status_label = tk.Label(top, text="Waiting...")
    status_label.pack(side="left")

    grid = tk.Frame(root)
    grid.pack()

    buttons.clear()

    for r in range(3):
        row = []
        for c in range(3):
            b = tk.Button(
                grid,
                text=" ",
                width=10,
                height=4,
                command=lambda r=r, c=c: send(f"MOVE {r} {c}")
            )
            b.grid(row=r, column=c)
            row.append(b)
        buttons.append(row)

    ui_ready = True

    if last_state:
        update_board(last_state)

def update_board(state):
    global buttons, ui_ready

    if not ui_ready or len(buttons) != 3:
        return

    cells = state.split(",")

    if len(cells) != 9:
        return

    for i in range(9):
        r = i // 3
        c = i % 3
        if r < len(buttons) and c < len(buttons[r]):
            buttons[r][c]["text"] = cells[i]

def receive():
    global symbol, last_state

    while True:
        msg = recv()
        if not msg:
            continue

        for line in msg.split("\n"):

            if line == "SUCCESS":
                root.after(0, choose_photo)

            elif line == "PHOTO_OK":
                root.after(0, build_game_ui)

            elif line == "WAIT":
                root.after(0, lambda: status_label and status_label.config(text="Waiting for opponent..."))

            elif line == "START":
                root.after(0, lambda: status_label and status_label.config(text="Game started"))

            elif line.startswith("SYMBOL"):
                symbol = line.split()[1]

            elif line.startswith("BOARD"):
                state = line.split(" ", 1)[1]
                last_state = state
                root.after(0, update_board, state)

            elif line.startswith("WIN"):
                root.after(0, lambda: messagebox.showinfo("Game", "You win!"))

            elif line == "DRAW":
                root.after(0, lambda: messagebox.showinfo("Game", "Draw"))

threading.Thread(target=receive, daemon=True).start()

choose_action()
root.mainloop()