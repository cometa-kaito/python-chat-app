import socket
import threading
import json
from datetime import datetime
import os
import google.generativeai as genai

# --- 設定 ---
HOST = '0.0.0.0'
PORT = 12345
CHAT_LOG_FILE = "chat_log.json"
# ---

# --- Gemini API 設定 ---
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        print("[WARNING] 環境変数 'GEMINI_API_KEY' が設定されていません。AI機能は利用できません。")
        GEMINI_API_KEY = None
    else:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("[INFO] Gemini APIの準備が完了しました。")
except Exception as e:
    print(f"[ERROR] Gemini APIの初期化に失敗しました: {e}")
    GEMINI_API_KEY = None
# ---

clients = []
client_info = {}
board_messages = []

# =================================================================
# ===== 新しい通信プロトコル用のヘルパー関数 (ここから) =====
# =================================================================

def receive_message(client_socket):
    """ヘッダーからメッセージ長を読み取り、完全なメッセージを受信する"""
    try:
        # 4バイトのヘッダーを受信してメッセージ長を取得
        header = client_socket.recv(4)
        if not header:
            return None
        msg_len = int.from_bytes(header, 'big')

        # メッセージ本体を、指定された長さになるまで受信し続ける
        chunks = []
        bytes_recd = 0
        while bytes_recd < msg_len:
            chunk = client_socket.recv(min(msg_len - bytes_recd, 4096))
            if not chunk:
                return None # 接続が途中で切れた
            chunks.append(chunk)
            bytes_recd += len(chunk)
        
        full_message = b''.join(chunks)
        return json.loads(full_message.decode('utf-8'))
    except (ConnectionResetError, ConnectionAbortedError):
        return None
    except Exception as e:
        print(f"[ERROR] メッセージの受信に失敗しました: {e}")
        return None

def send_message(client_socket, message_dict):
    """メッセージをJSONに変換し、ヘッダーを付けて送信する"""
    try:
        message_json = json.dumps(message_dict)
        message_bytes = message_json.encode('utf-8')
        # メッセージの長さを4バイトのヘッダーとして作成
        header = len(message_bytes).to_bytes(4, 'big')
        # ヘッダーとメッセージ本体を送信
        client_socket.sendall(header + message_bytes)
        return True
    except (ConnectionResetError, ConnectionAbortedError):
        return False
    except Exception as e:
        print(f"[ERROR] メッセージの送信に失敗しました: {e}")
        return False

# =================================================================
# ===== 新しい通信プロトコル用のヘルパー関数 (ここまで) =====
# =================================================================


def call_gemini_api(history):
    if not GEMINI_API_KEY: return "AI機能が設定されていません。"
    prompt_history = "\n".join([f"{msg['username']}: {msg['message']}" for msg in history[-10:]])
    prompt = f"あなたはフレンドリーなAIアシスタントです。\n以下のチャット履歴を読んで、会話の流れを簡単に要約し、次にみんなで話すと盛り上がりそうな新しいトピックをいくつか提案してください。\n\n--- チャット履歴 ---\n{prompt_history}\n--- ここまで ---\n\n提案は、箇条書きなどを使って分かりやすく、親しみやすい口調でお願いします。"
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"[ERROR] Gemini APIの呼び出しでエラーが発生しました: {e}")
        return "AIアシスタントの呼び出し中にエラーが発生しました。"

def load_chat_log():
    if not os.path.exists(CHAT_LOG_FILE): return []
    try:
        with open(CHAT_LOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            return json.loads(content) if content else []
    except (json.JSONDecodeError, IOError): return []

def save_chat_log():
    try:
        with open(CHAT_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(board_messages, f, indent=4, ensure_ascii=False)
    except IOError: pass

def broadcast_board_info():
    """全クライアントに最新の掲示板情報をブロードキャストする"""
    message_to_send = {"command": "BoardInfo", "payload": board_messages}
    # clientsリストのコピーに対してループ処理を行い、安全に要素を削除できるようにする
    for client_socket in list(clients):
        if not send_message(client_socket, message_to_send):
            # 送信に失敗したクライアントは切断されたとみなす
            remove_client(client_socket)

def remove_client(client_socket):
    if client_socket in clients:
        clients.remove(client_socket)
    user_to_remove = None
    for username, sock in client_info.items():
        if sock == client_socket:
            user_to_remove = username
            break
    if user_to_remove:
        del client_info[user_to_remove]
        print(f"[INFO] {user_to_remove} が切断しました。")
        board_messages.append({"username": "Server", "message": f"{user_to_remove} が退出しました。", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        save_chat_log()
        broadcast_board_info() # 退出を全員に通知

def handle_client(client_socket, addr):
    print(f"[INFO] {addr} から新しい接続がありました。")
    username = ""
    try:
        # クライアントに接続開始を通知
        send_message(client_socket, {"command": "ConnectionStart"})
        
        while True:
            # クライアントからのメッセージを新しい方式で受信
            msg = receive_message(client_socket)
            if msg is None:
                break # 接続が切れた
            
            command = msg.get("command")
            payload = msg.get("payload")

            if command == "UserName":
                username = payload
                client_info[username] = client_socket
                print(f"[INFO] {addr} のユーザー名は {username} です。")
                send_message(client_socket, {"command": "NameRecieved", "payload": username})
                board_messages.append({"username": "Server", "message": f"{username} が参加しました。", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                save_chat_log()
                broadcast_board_info()
            
            elif command == "Send":
                print(f"[MESSAGE] {username}: {payload}")
                message = {"username": username, "message": payload, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                board_messages.append(message)
                save_chat_log()
                broadcast_board_info()
            
            elif command == "AI_HELP":
                print(f"[AI] {username} がAIアシスタントを呼び出しました。")
                ai_response = call_gemini_api(board_messages)
                ai_message = {"username": "AI Assistant", "message": ai_response, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                board_messages.append(ai_message)
                save_chat_log()
                broadcast_board_info()
            
            elif command == "End":
                print(f"[INFO] {username} が正常に接続を終了しました。")
                break
    finally:
        remove_client(client_socket)
        client_socket.close()

def main():
    global board_messages
    board_messages = load_chat_log()
    print(f"[INFO] 過去のチャットログを {len(board_messages)} 件読み込みました。")
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(10)
        print(f"[INFO] サーバーが {HOST}:{PORT} で起動しました。")
        while True:
            client_socket, addr = server_socket.accept()
            clients.append(client_socket)
            thread = threading.Thread(target=handle_client, args=(client_socket, addr))
            thread.daemon = True
            thread.start()
    except KeyboardInterrupt:
        print("\n[INFO] サーバーを停止します。")
    except Exception as e:
        print(f"[FATAL] サーバーの起動に失敗しました: {e}")
    finally:
        print("[INFO] 最終的なチャットログを保存しています...")
        save_chat_log()
        for client in clients:
            client.close()
        server_socket.close()

if __name__ == "__main__":
    main()