import socket
import threading
import tkinter as tk
from tkinter import simpledialog, scrolledtext, messagebox
import json

# --- 設定 ---
HOST = '127.0.0.1'  # 接続先のサーバーアドレス
PORT = 12345
# ---

class ChatClient:
    def __init__(self, master):
        self.master = master
        master.title("掲示板チャット")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = ""
        self.is_connected = False

        # --- GUIのセットアップ ---
        self.chat_box = scrolledtext.ScrolledText(master, state='disabled', width=60, height=20)
        self.chat_box.pack(padx=10, pady=10)

        self.msg_entry = tk.Entry(master, width=50)
        self.msg_entry.pack(side=tk.LEFT, padx=(10, 0), pady=(0, 10), fill=tk.X, expand=True)
        self.msg_entry.bind("<Return>", self.send_message)

        self.send_button = tk.Button(master, text="送信", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT, padx=(5, 10), pady=(0, 10))

        # ウィンドウを閉じる際のイベントを設定
        master.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # master(ウィンドウ)の準備ができてから接続処理を開始
        master.after(100, self.start_connection)

    def start_connection(self):
        """サーバーへの接続とログイン処理（メインスレッドで実行）"""
        try:
            # 1. サーバーへ接続
            self.sock.connect((HOST, PORT))

            # 2. サーバーから 'Connection Start' を待つ
            data = self.sock.recv(1024).decode('utf-8')
            if not data.startswith("Connection Start"):
                messagebox.showerror("接続エラー", "サーバーからの応答が不正です。")
                self.master.destroy()
                return

            # 3. ユーザー名を入力させる (GUI操作なのでメインスレッドで安全)
            self.username = simpledialog.askstring("ユーザー名", "ユーザー名を入力してください:", parent=self.master)
            if not self.username:
                self.username = "Anonymous"
            self.master.title(f"掲示板チャット - {self.username}")

            # 4. サーバーにユーザー名を送信
            self.sock.sendall(f"UserName:{self.username}".encode('utf-8'))

            # 5. サーバーから 'NameRecieved' を待つ
            response = self.sock.recv(1024).decode('utf-8')
            if not response.startswith("NameRecieved"):
                 messagebox.showerror("接続エラー", "ユーザー名の登録に失敗しました。")
                 self.master.destroy()
                 return
            
            self.is_connected = True
            self.display_message(f"[INFO] サーバーに接続しました。({self.username})")

            # 6. ログイン完了後、メッセージ受信スレッドを開始
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

        except ConnectionRefusedError:
            messagebox.showerror("接続エラー", "サーバーに接続できませんでした。サーバーが起動しているか確認してください。")
            self.master.destroy()
        except Exception as e:
            messagebox.showerror("エラー", f"接続中にエラーが発生しました: {e}")
            self.master.destroy()

    def receive_messages(self):
        """サーバーからのメッセージを受信し続けるスレッド"""
        while self.is_connected:
            try:
                data = self.sock.recv(4096).decode('utf-8')
                if not data:
                    break
                
                # サーバーからのデータは常に BoardInfo のはず
                command, payload = data.split(':', 1)
                if command == "BoardInfo":
                    messages = json.loads(payload)
                    self.update_chat_box(messages)

            except (ConnectionAbortedError, ConnectionResetError):
                self.display_message("[ERROR] サーバーとの接続が切れました。")
                break
            except Exception as e:
                print(f"[ERROR] メッセージの受信中にエラーが発生しました: {e}")
                break
        
        self.sock.close()


    def send_message(self, event=None):
        if not self.is_connected:
            messagebox.showwarning("未接続", "まだサーバーに接続されていません。")
            return
            
        message = self.msg_entry.get()
        if message:
            try:
                self.sock.sendall(f"Send:{message}".encode('utf-8'))
                self.msg_entry.delete(0, tk.END)
            except socket.error as e:
                 self.display_message(f"[ERROR] 送信に失敗しました: {e}")

    def update_chat_box(self, messages):
        self.chat_box.config(state='normal')
        self.chat_box.delete(1.0, tk.END)
        for msg in messages:
            line = f"[{msg['timestamp']}] {msg['username']}: {msg['message']}\n"
            self.chat_box.insert(tk.END, line)
        self.chat_box.yview(tk.END)
        self.chat_box.config(state='disabled')

    def display_message(self, message):
        self.chat_box.config(state='normal')
        self.chat_box.insert(tk.END, message + "\n")
        self.chat_box.yview(tk.END)
        self.chat_box.config(state='disabled')

    def on_closing(self):
        if self.is_connected:
            try:
                self.sock.sendall("End:".encode('utf-8'))
            except socket.error:
                pass # 既に切れていても無視
        self.is_connected = False
        self.sock.close()
        self.master.destroy()

def main():
    root = tk.Tk()
    client = ChatClient(root)
    root.mainloop()

if __name__ == "__main__":
    main()