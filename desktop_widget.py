import tkinter as tk
def create_widget():
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.8)
    root.geometry("100x100+20+20")
    root.configure(bg='black')
    lbl = tk.Label(root, text="JARVIS\nMK-II", fg="#00f0ff", bg="black", font=("Courier", 12, "bold"))
    lbl.pack(expand=True, fill='both')
    root.mainloop()
if __name__ == '__main__':
    create_widget()
