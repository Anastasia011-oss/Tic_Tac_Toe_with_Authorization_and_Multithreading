import socket
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk

HOST = "127.0.0.1"
PORT = 5001

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((HOST, PORT))

symbol = ""
buttons = []
root = tk.Tk()
root.withdraw()
current_window = None
avatar_photo = None

def choose_action():
    global current_window
    if current_window: current_window.destroy()

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

    def send():
        email = email_entry.get()
        password = pass_entry.get()
        client.sendall(f"{mode} {email} {password}\n".encode())

    tk.Button(win, text="Отправить", command=send).pack(pady=10)
    tk.Button(win, text="Назад", command=choose_action).pack(pady=5)

def choose_photo():
    global avatar_photo
    path = filedialog.askopenfilename()
    if not path:
        messagebox.showerror("Ошибка", "Выберите фото обязательно!")
        return choose_photo()

    with open(path, "rb") as f:
        data = f.read()

    size = len(data)
    client.sendall(f"PHOTO {size}\n".encode())
    client.sendall(data)

    img = Image.open(path)
    img = img.resize((60, 60))
    avatar_photo = ImageTk.PhotoImage(img)

def build_game_ui():
    global current_window
    if current_window: current_window.destroy()
    root.deiconify()
    root.title("Tic Tac Toe")

    top_frame = tk.Frame(root)
    top_frame.pack(side="top", fill="x", pady=10)

    if avatar_photo:
        avatar_label = tk.Label(top_frame, image=avatar_photo)
        avatar_label.image = avatar_photo
        avatar_label.pack(side="left", padx=10)

    status_label.pack(in_=top_frame, side="left", padx=10)

    frame.pack(side="top", pady=20)

def click(r, c):
    try: client.sendall(f"MOVE {r} {c}\n".encode())
    except: pass

def update_board(state):
    cells = state.split(",")
    for i in range(9):
        r = i // 3
        c = i % 3
        buttons[r][c]["text"] = cells[i]

def receive():
    global symbol
    buffer = ""
    while True:
        try:
            data = client.recv(1024).decode()
        except:
            print("Сервер отключился")
            break
        if not data: break

        buffer += data
        while "\n" in buffer:
            msg, buffer = buffer.split("\n",1)
            if msg.startswith("ERROR"):
                root.after(0, lambda: messagebox.showerror("Ошибка", msg))
            elif msg=="OK":
                root.after(0, lambda: messagebox.showinfo("Успех","Регистрация успешна"))
            elif msg=="SUCCESS":
                root.after(0, choose_photo)
            elif msg=="PHOTO_OK":
                root.after(0, build_game_ui)
            elif msg=="WAIT":
                root.after(0, lambda: status_label.config(text="Waiting for opponent..."))
            elif msg=="START":
                root.after(0, lambda: status_label.config(text="Game started"))
            elif msg.startswith("SYMBOL"):
                symbol = msg.split()[1]
                root.after(0, lambda: root.title(f"You are {symbol}"))
            elif msg.startswith("BOARD"):
                state = msg.split(" ",1)[1]
                root.after(0, update_board,state)
            elif msg.startswith("WIN"):
                root.after(0, lambda: messagebox.showinfo("Game","Win"))
            elif msg=="DRAW":
                root.after(0, lambda: messagebox.showinfo("Game","Draw"))
            elif msg=="OPPONENT_LEFT":
                root.after(0, lambda: messagebox.showinfo("Game","Opponent left"))

status_label = tk.Label(root,text="")
frame = tk.Frame(root)
for r in range(3):
    row = []
    for c in range(3):
        btn = tk.Button(frame,text=" ", width=10, height=4, command=lambda r=r,c=c: click(r,c))
        btn.grid(row=r,column=c)
        row.append(btn)
    buttons.append(row)

choose_action()
threading.Thread(target=receive, daemon=True).start()
root.mainloop()