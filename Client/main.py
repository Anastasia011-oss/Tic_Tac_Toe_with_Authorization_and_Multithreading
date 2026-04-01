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
status_label = None
ui_ready = False
last_state = None
photo_sent = False

root = tk.Tk()
root.withdraw()

avatars = [None, None]
avatar_labels = []
current_window = None


def choose_action():
    global current_window

    if current_window:
        current_window.destroy()

    win = tk.Toplevel()
    current_window = win
    win.title("Выбор")

    tk.Button(win, text="Войти",
              command=lambda: open_auth(win, "LOGIN")).pack(pady=5)

    tk.Button(win, text="Регистрация",
              command=lambda: open_auth(win, "REGISTER")).pack(pady=5)


def open_auth(prev, mode):
    prev.destroy()

    win = tk.Toplevel()
    win.title(mode)

    tk.Label(win, text="Email").pack()
    email = tk.Entry(win)
    email.pack()

    tk.Label(win, text="Пароль").pack()
    pw = tk.Entry(win, show="*")
    pw.pack()

    tk.Button(win, text="OK",
              command=lambda: send(f"{mode} {email.get()} {pw.get()}")).pack(pady=5)


def choose_photo():
    global photo_sent

    path = filedialog.askopenfilename()
    if not path:
        messagebox.showerror("Ошибка", "Выберите фото!")
        return

    with open(path, "rb") as f:
        data = f.read()

    send(f"UPLOAD_PHOTO {base64.b64encode(data).decode()}")

    img = Image.open(path).resize((60, 60))
    photo = ImageTk.PhotoImage(img)

    avatars[0] = photo
    photo_sent = True


def build_game_ui():
    global status_label, buttons, ui_ready, last_state, avatar_labels

    root.deiconify()

    for widget in root.winfo_children():
        widget.destroy()

    top = tk.Frame(root)
    top.pack()

    avatar_labels.clear()

    for i in range(2):
        lbl = tk.Label(top)
        lbl.pack(side="left", padx=5)
        avatar_labels.append(lbl)

        if avatars[i]:
            lbl.config(image=avatars[i])
            lbl.image = avatars[i]

    status_label = tk.Label(top, text="Waiting for opponent...")
    status_label.pack(side="left", padx=10)

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
    if not ui_ready:
        return

    cells = state.split(",")
    if len(cells) != 9:
        return

    for i in range(9):
        r = i // 3
        c = i % 3
        buttons[r][c]["text"] = cells[i]


def receive():
    global symbol, last_state

    while True:
        msg = recv()
        print("RECV:", msg)

        if msg is None:
            break

        for line in msg.split("\n"):
            line = line.strip()
            if not line:
                continue

            print("LINE:", line)

            if line == "NEED_PHOTO":
                if not photo_sent:
                    root.after(0, choose_photo)

            elif line == "SUCCESS":
                root.after(0, build_game_ui)

                if not photo_sent:
                    root.after(0, choose_photo)

            elif line == "WAIT":
                root.after(0, lambda: (
                    status_label.config(text="Waiting for opponent...")
                    if status_label else None
                ))

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

            elif line.startswith("ERROR"):
                root.after(0, lambda: messagebox.showerror("Error", line))


threading.Thread(target=receive, daemon=True).start()

choose_action()
root.mainloop()