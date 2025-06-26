import socket
import threading
import tkinter as tk
from tkinter import simpledialog, scrolledtext, messagebox
import json
import os
from datetime import datetime

# --- 設定 ---
HOST = '10.101.223.218'  # サーバーPCのIPアドレス
PORT = 12345
HISTORY_FILE = "my_chat_history.json"
# ---

# =================================================================
# ===== 新しい通信プロトコル用のヘルパー関数 (ここから) =====
# =================================================================

def receive_message(client_socket):
    """ヘッダーからメッセージ長を読み取り、完全なメッセージを受信する"""
    try:
        header = client_socket.recv(4)
        if not header: return None
        msg_len = int.from_bytes(header, 'big')
        chunks = []
        bytes_recd = 0
        while bytes_recd < msg_len:
            chunk = client_socket.recv(min(msg_len - bytes_recd, 4096))
            if not chunk: return None
            chunks.append(chunk)
            bytes_recd += len(chunk)
        full_message = b''.join(chunks)
        return json.loads(full_message.decode('utf-8'))
    except (ConnectionResetError, ConnectionAbortedError, OSError):
        return None
    except Exception:
        return None

def send_message_to_server(client_socket, message_dict):
    """メッセージをJSONに変換し、ヘッダーを付けて送信する"""
    try:
        message_json = json.dumps(message_dict)
        message_bytes = message_json.encode('utf-8')
        header = len(message_bytes).to_bytes(4, 'big')
        client_socket.sendall(header + message_bytes)
        return True
    except (ConnectionResetError, ConnectionAbortedError, OSError):
        return False
    except Exception:
        return False

# =================================================================
# ===== 新しい通信プロトコル用のヘルパー関数 (ここまで) =====
# =================================================================

class ChatClient:
    def __init__(self, master):
        self.master = master
        master.title("掲示板チャット")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = ""
        self.is_connected = False
        self.my_history = self.load_my_history()

        self.chat_box = scrolledtext.ScrolledText(master, state='disabled', width=60, height=20, wrap=tk.WORD)
        self.chat_box.pack(padx=10, pady=10)
        self.chat_box.tag_config('me', justify='right', background='#E0F7FA', rmargin=10)
        self.chat_box.tag_config('other', justify='left', lmargin1=10, lmargin2=10)
        self.chat_box.tag_config('server', justify='center', foreground='gray')
        self.chat_box.tag_config('ai', justify='left', background='#E8F5E9', lmargin1=10, lmargin2=10, wrap='word')

        bottom_frame = tk.Frame(master)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.msg_entry = tk.Entry(bottom_frame)
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.msg_entry.bind("<Return>", self.send_message_action)
        self.send_button = tk.Button(bottom_frame, text="送信", command=self.send_message_action)
        self.send_button.pack(side=tk.LEFT, padx=5)
        self.ai_button = tk.Button(bottom_frame, text="AIお助け", command=self.request_ai_help)
        self.ai_button.pack(side=tk.LEFT)

        master.protocol("WM_DELETE_WINDOW", self.on_closing)
        master.after(100, self.start_connection)

    def request_ai_help(self):
        if not self.is_connected:
            messagebox.showwarning("未接続", "サーバーとの接続が切れています。")
            return
        if messagebox.askokcancel("AIお助け", "AIアシスタントに話題を提案してもらいますか？"):
            if not send_message_to_server(self.sock, {"command": "AI_HELP"}):
                self.handle_disconnect()

    def load_my_history(self):
        if not os.path.exists(HISTORY_FILE): return []
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                return json.loads(content) if content else []
        except (json.JSONDecodeError, IOError): return []

    def save_my_history(self):
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.my_history, f, indent=4, ensure_ascii=False)
        except IOError: pass

    def start_connection(self):
        try:
            self.sock.connect((HOST, PORT))
            
            # サーバーからの接続開始通知を待つ
            msg = receive_message(self.sock)
            if msg is None or msg.get("command") != "ConnectionStart":
                messagebox.showerror("接続エラー", "サーバーからの応答が不正です。")
                self.master.destroy()
                return

            self.username = simpledialog.askstring("ユーザー名", "ユーザー名を入力してください:", parent=self.master)
            if not self.username: self.username = "Anonymous"
            self.master.title(f"掲示板チャット - {self.username}")
            
            # ユーザー名をサーバーに送信
            send_message_to_server(self.sock, {"command": "UserName", "payload": self.username})
            
            # ユーザー名登録完了通知を待つ
            response = receive_message(self.sock)
            if response is None or response.get("command") != "NameRecieved":
                 messagebox.showerror("接続エラー", "ユーザー名の登録に失敗しました。")
                 self.master.destroy()
                 return
            
            self.is_connected = True
            self.display_message("[INFO] サーバーに接続しました。", "server")
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()
        except ConnectionRefusedError:
            messagebox.showerror("接続エラー", "サーバーに接続できませんでした。")
            self.master.destroy()
        except Exception as e:
            messagebox.showerror("エラー", f"接続中にエラーが発生しました: {e}")
            self.master.destroy()

    def receive_messages(self):
        while self.is_connected:
            msg = receive_message(self.sock)
            if msg is None:
                self.handle_disconnect()
                break
            
            command = msg.get("command")
            if command == "BoardInfo":
                payload = msg.get("payload", [])
                self.master.after(0, self.update_chat_box, payload)

    def handle_disconnect(self):
        if not self.is_connected: return
        self.is_connected = False
        self.master.after(0, self._perform_disconnect_tasks)

    def _perform_disconnect_tasks(self):
        self.display_message("[ERROR] サーバーとの接続が切れました。", "server")
        self.msg_entry.config(state='disabled')
        self.send_button.config(state='disabled')
        self.ai_button.config(state='disabled')
        self.master.title(f"掲示板チャット - {self.username} (切断)")
        try:
            self.sock.close()
        except socket.error: pass

    def send_message_action(self, event=None):
        if not self.is_connected:
            messagebox.showwarning("未接続", "サーバーとの接続が切れています。")
            return
        message = self.msg_entry.get()
        if message:
            msg_data = {"username": self.username, "message": message, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            if send_message_to_server(self.sock, {"command": "Send", "payload": message}):
                self.my_history.append(msg_data)
                self.save_my_history()
                self.msg_entry.delete(0, tk.END)
            else:
                self.handle_disconnect()

    def update_chat_box(self, messages):
        self.chat_box.config(state='normal')
        self.chat_box.delete(1.0, tk.END)
        all_messages = messages + self.my_history
        unique_messages = list({m.get('timestamp', '') + m.get('message', ''): m for m in all_messages if m.get('timestamp') and m.get('message')}.values())
        sorted_messages = sorted(unique_messages, key=lambda x: x['timestamp'])
        for msg in sorted_messages:
            username = msg.get("username", "Unknown")
            message = msg.get("message", "")
            timestamp = msg.get("timestamp", "")
            if username == self.username: tag = 'me'; line = f"{message}\n"
            elif username == "Server": tag = 'server'; line = f"--- {message} ---\n"
            elif username == "AI Assistant": tag = 'ai'; line = f"AI Assistant:\n{message}\n"
            else: tag = 'other'; line = f"{username}: {message}\n"
            self.chat_box.insert(tk.END, line, tag)
            self.chat_box.insert(tk.END, f"[{timestamp}]\n\n", (tag, 'time'))
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
            send_message_to_server(self.sock, {"command": "End"})
        self.is_connected = False
        self.sock.close()
        self.save_my_history()
        self.master.destroy()

def main():
    root = tk.Tk()
    ChatClient(root)
    root.mainloop()

if __name__ == "__main__":
    main()