import socket
import threading
import tkinter as tk
from tkinter import simpledialog, scrolledtext, messagebox, filedialog
import json
import os
from datetime import datetime
import base64
from io import BytesIO
from PIL import Image, ImageTk

# --- 設定 ---
HOST = '10.101.223.218'  # サーバーPCのIPアドレス
PORT = 12345
HISTORY_FILE = "my_chat_history.json"
# ---

# =================================================================
# ===== 通信プロトコル用のヘルパー関数 (変更なし) =====
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

class ChatClient:
    def __init__(self, master):
        self.master = master
        master.title("掲示板チャット")
        # ウィンドウの最小サイズを設定
        master.minsize(400, 300)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = ""
        self.is_connected = False
        self.my_history = self.load_my_history()
        # PhotoImageオブジェクトがGCされるのを防ぐためのキャッシュ
        self.image_cache = []

        # --- UIの配置 (レスポンシブ対応) ---
        main_frame = tk.Frame(master)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # グリッドレイアウトでリサイズに対応
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        self.chat_box = scrolledtext.ScrolledText(main_frame, state='disabled', wrap=tk.WORD)
        self.chat_box.grid(row=0, column=0, sticky="nsew")

        # タグの設定
        self.chat_box.tag_config('me', justify='right', background='#E0F7FA', rmargin=10)
        self.chat_box.tag_config('other', justify='left', lmargin1=10, lmargin2=10)
        self.chat_box.tag_config('server', justify='center', foreground='gray')
        self.chat_box.tag_config('ai', justify='left', background='#E8F5E9', lmargin1=10, lmargin2=10, wrap='word')
        self.chat_box.tag_config('time', foreground='gray', font=('TkDefaultFont', 8))

        bottom_frame = tk.Frame(main_frame)
        bottom_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        bottom_frame.columnconfigure(0, weight=1)

        self.msg_entry = tk.Entry(bottom_frame)
        self.msg_entry.grid(row=0, column=0, sticky="ew")
        self.msg_entry.bind("<Return>", self.send_message_action)

        # ボタンを配置するフレーム
        button_frame = tk.Frame(bottom_frame)
        button_frame.grid(row=0, column=1, padx=(5, 0))

        self.send_button = tk.Button(button_frame, text="送信", command=self.send_message_action)
        self.send_button.pack(side=tk.LEFT)
        
        # [新機能] 画像送信ボタン
        self.image_button = tk.Button(button_frame, text="画像", command=self.select_and_send_image)
        self.image_button.pack(side=tk.LEFT, padx=5)

        self.ai_button = tk.Button(button_frame, text="AIお助け", command=self.request_ai_help)
        self.ai_button.pack(side=tk.LEFT)
        # --- UI設定ここまで ---

        master.protocol("WM_DELETE_WINDOW", self.on_closing)
        master.after(100, self.start_connection)

    def request_ai_help(self):
        """[機能追加] AIへの指示を入力させてサーバーに送信する"""
        if not self.is_connected:
            messagebox.showwarning("未接続", "サーバーとの接続が切れています。")
            return
        
        # プロンプト入力ダイアログを表示
        prompt = simpledialog.askstring("AIお助け", "AIへの指示や質問を入力してください:", parent=self.master)
        
        if prompt: # ユーザーが何か入力した場合
            if not send_message_to_server(self.sock, {"command": "AI_HELP", "payload": prompt}):
                self.handle_disconnect()

    def select_and_send_image(self):
        """[新機能] 画像を選択してサーバーに送信する"""
        if not self.is_connected:
            messagebox.showwarning("未接続", "サーバーとの接続が切れています。")
            return
        
        file_path = filedialog.askopenfilename(
            title="画像を選択",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.gif")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "rb") as image_file:
                # 送信前に画像をリサイズして負荷を軽減
                img = Image.open(image_file)
                img.thumbnail((300, 300))  # 300x300ピクセルに収まるようにリサイズ
                
                buffered = BytesIO()
                # 透過情報を保持できるPNG形式で統一
                img.save(buffered, format="PNG")
                # Base64エンコードして文字列として送信
                img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # サーバーに画像データを送信
            if not send_message_to_server(self.sock, {"command": "SendImage", "payload": img_str}):
                self.handle_disconnect()

        except Exception as e:
            messagebox.showerror("エラー", f"画像の処理中にエラーが発生しました: {e}")

    def update_chat_box(self, messages):
        """[機能追加] 画像メッセージの表示に対応"""
        self.chat_box.config(state='normal')
        self.chat_box.delete(1.0, tk.END)

        all_messages = messages + self.my_history
        unique_messages = list({m.get('timestamp', '') + m.get('message', '') + m.get('image_data', ''): m for m in all_messages if m.get('timestamp')}.values())
        sorted_messages = sorted(unique_messages, key=lambda x: x['timestamp'])

        for msg in sorted_messages:
            username = msg.get("username", "Unknown")
            message = msg.get("message", "")
            image_data = msg.get("image_data") # 画像データ
            timestamp = msg.get("timestamp", "")
            
            tag = 'other'
            if username == self.username: tag = 'me'
            elif username == "Server": tag = 'server'
            elif username == "AI Assistant": tag = 'ai'

            # --- メッセージ/画像の挿入 ---
            if image_data:
                # 画像メッセージの処理
                try:
                    name_line = "" if tag == 'me' else f"{username}:\n"
                    self.chat_box.insert(tk.END, name_line, tag)
                    
                    img_bytes = base64.b64decode(image_data)
                    img = Image.open(BytesIO(img_bytes))
                    photo = ImageTk.PhotoImage(img)
                    self.image_cache.append(photo) # GC対策
                    
                    self.chat_box.image_create(tk.END, image=photo, padx=5, pady=5)
                    self.chat_box.insert(tk.END, '\n')

                except Exception as e:
                    self.chat_box.insert(tk.END, f"[{username}から送信された画像を表示できません]\n", tag)
            else:
                # テキストメッセージの処理
                line = ""
                if tag == 'me': line = f"{message}\n"
                elif tag == 'server': line = f"--- {message} ---\n"
                elif tag == 'ai': line = f"AI Assistant:\n{message}\n"
                else: line = f"{username}: {message}\n"
                self.chat_box.insert(tk.END, line, tag)
            
            # --- タイムスタンプの挿入 ---
            time_tag = (tag, 'time')
            self.chat_box.insert(tk.END, f"[{timestamp}]\n\n", time_tag)
        
        self.chat_box.yview(tk.END)
        self.chat_box.config(state='disabled')


    def send_message_action(self, event=None):
        if not self.is_connected:
            messagebox.showwarning("未接続", "サーバーとの接続が切れています。")
            return
        message = self.msg_entry.get()
        if message:
            # 自分用の履歴には保存しない（サーバーからの情報で統一するため）
            if send_message_to_server(self.sock, {"command": "Send", "payload": message}):
                self.msg_entry.delete(0, tk.END)
            else:
                self.handle_disconnect()

    # --- 以下、既存の関数 (一部軽微な修正) ---
    def load_my_history(self):
        # このサンプルではクライアント側での履歴保存は不要になるため空リストを返す
        return []

    def save_my_history(self):
        # このサンプルではクライアント側での履歴保存は不要
        pass

    def start_connection(self):
        try:
            self.sock.connect((HOST, PORT))
            msg = receive_message(self.sock)
            if msg is None or msg.get("command") != "ConnectionStart":
                messagebox.showerror("接続エラー", "サーバーからの応答が不正です。")
                self.master.destroy()
                return

            self.username = simpledialog.askstring("ユーザー名", "ユーザー名を入力してください:", parent=self.master)
            if not self.username: self.username = "Anonymous"
            self.master.title(f"掲示板チャット - {self.username}")
            
            send_message_to_server(self.sock, {"command": "UserName", "payload": self.username})
            
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
        self.image_button.config(state='disabled')
        self.master.title(f"掲示板チャット - {self.username} (切断)")
        try:
            self.sock.close()
        except socket.error: pass

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
        self.master.destroy()

def main():
    root = tk.Tk()
    ChatClient(root)
    root.mainloop()

if __name__ == "__main__":
    main()