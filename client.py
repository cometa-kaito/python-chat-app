import socket
import threading
import tkinter as tk
from tkinter import simpledialog, scrolledtext, messagebox
import json
import os

# --- 設定 ---
HOST = '127.0.0.1'
PORT = 12345
HISTORY_FILE = "my_chat_history.json" # 自分の送信履歴を保存するファイル
# ---

class ChatClient:
    def __init__(self, master):
        self.master = master
        master.title("掲示板チャット")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = ""
        self.is_connected = False
        self.my_history = self.load_my_history() # 自分の送信履歴を読み込む

        # --- GUIのセットアップ ---
        self.chat_box = scrolledtext.ScrolledText(master, state='disabled', width=60, height=20, wrap=tk.WORD)
        self.chat_box.pack(padx=10, pady=10)
        
        # メッセージのスタイル定義（タグ設定）
        # 自分（右寄せ、薄い青色）
        self.chat_box.tag_config('me', justify='right', background='#E0F7FA', rmargin=10)
        # 他人（左寄せ、白色）
        self.chat_box.tag_config('other', justify='left', lmargin1=10, lmargin2=10)
        # サーバーメッセージ（中央寄せ、薄い灰色）
        self.chat_box.tag_config('server', justify='center', foreground='gray')


        self.msg_entry = tk.Entry(master, width=50)
        self.msg_entry.pack(side=tk.LEFT, padx=(10, 0), pady=(0, 10), fill=tk.X, expand=True)
        self.msg_entry.bind("<Return>", self.send_message)

        self.send_button = tk.Button(master, text="送信", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT, padx=(5, 10), pady=(0, 10))

        master.protocol("WM_DELETE_WINDOW", self.on_closing)
        master.after(100, self.start_connection)

    def load_my_history(self):
        """自分の送信履歴を読み込む"""
        if not os.path.exists(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                return json.loads(content) if content else []
        except (json.JSONDecodeError, IOError):
            return []

    def save_my_history(self):
        """自分の送信履歴を保存する"""
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.my_history, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"[ERROR] 送信履歴の保存に失敗: {e}")

    def start_connection(self):
        """サーバーへの接続とログイン処理"""
        try:
            self.sock.connect((HOST, PORT))
            data = self.sock.recv(1024).decode('utf-8')
            if not data.startswith("Connection Start"):
                messagebox.showerror("接続エラー", "サーバーからの応答が不正です。")
                self.master.destroy()
                return

            self.username = simpledialog.askstring("ユーザー名", "ユーザー名を入力してください:", parent=self.master)
            if not self.username:
                self.username = "Anonymous"
            self.master.title(f"掲示板チャット - {self.username}")

            self.sock.sendall(f"UserName:{self.username}".encode('utf-8'))
            response = self.sock.recv(1024).decode('utf-8')
            if not response.startswith("NameRecieved"):
                 messagebox.showerror("接続エラー", "ユーザー名の登録に失敗しました。")
                 self.master.destroy()
                 return
            
            self.is_connected = True
            self.display_message("[INFO] サーバーに接続しました。", "server")

            # ログイン完了後、メッセージ受信スレッドを開始
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
                
                command, payload = data.split(':', 1)
                if command == "BoardInfo":
                    messages = json.loads(payload)
                    # UI更新はメインスレッドに任せる
                    self.master.after(0, self.update_chat_box, messages)

            except (ConnectionAbortedError, ConnectionResetError):
                self.master.after(0, self.display_message, "[ERROR] サーバーとの接続が切れました。", "server")
                break
            except Exception:
                break
        
        self.sock.close()

    def send_message(self, event=None):
        if not self.is_connected:
            messagebox.showwarning("未接続", "まだサーバーに接続されていません。")
            return
            
        message = self.msg_entry.get()
        if message:
            try:
                # サーバーに送信
                self.sock.sendall(f"Send:{message}".encode('utf-8'))
                
                # 自分の送信履歴に追加して保存
                msg_data = {
                    "username": self.username,
                    "message": message,
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                self.my_history.append(msg_data)
                self.save_my_history()

                self.msg_entry.delete(0, tk.END)
            except socket.error as e:
                 self.display_message(f"[ERROR] 送信に失敗しました: {e}", "server")

    def update_chat_box(self, messages):
        self.chat_box.config(state='normal')
        self.chat_box.delete(1.0, tk.END)

        # サーバーからの全メッセージと自分の履歴を結合し、タイムスタンプでソート
        all_messages = messages + self.my_history
        # 重複を削除 (同じタイムスタンプとメッセージを持つものを一つにする)
        unique_messages = list({m['timestamp'] + m['message']: m for m in all_messages}.values())
        # 時間順にソート
        sorted_messages = sorted(unique_messages, key=lambda x: x['timestamp'])

        for msg in sorted_messages:
            username = msg.get("username", "Unknown")
            message = msg.get("message", "")
            timestamp = msg.get("timestamp", "")
            
            # タグを決定
            if username == self.username:
                tag = 'me'
                line = f"{message}\n" # 自分のメッセージは名前を省略
            elif username == "Server":
                tag = 'server'
                line = f"--- {message} ---\n"
            else:
                tag = 'other'
                line = f"{username}: {message}\n"
            
            self.chat_box.insert(tk.END, line, tag)
            self.chat_box.insert(tk.END, f"[{timestamp}]\n\n", (tag, 'time')) # 時間表示用のタグ

        self.chat_box.tag_config('time', foreground='gray', font=('TkDefaultFont', 8))

        self.chat_box.yview(tk.END)
        self.chat_box.config(state='disabled')

    def display_message(self, message, tag):
        self.chat_box.config(state='normal')
        self.chat_box.insert(tk.END, message + "\n", tag)
        self.chat_box.yview(tk.END)
        self.chat_box.config(state='disabled')

    def on_closing(self):
        if self.is_connected:
            try:
                self.sock.sendall("End:".encode('utf-8'))
            except socket.error:
                pass
        self.is_connected = False
        self.sock.close()
        self.save_my_history() # 終了時に履歴を保存
        self.master.destroy()

def main():
    root = tk.Tk()
    ChatClient(root)
    root.mainloop()

if __name__ == "__main__":
    from datetime import datetime # send_messageで使うのでインポート
    main()