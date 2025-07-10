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
# ===== 通信プロトコル用のヘルパー関数 (変更なし) =====
# =================================================================
def receive_message(client_socket):
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
    except (ConnectionResetError, ConnectionAbortedError):
        return None
    except Exception as e:
        print(f"[ERROR] メッセージの受信に失敗しました: {e}")
        return None

def send_message(client_socket, message_dict):
    try:
        message_json = json.dumps(message_dict)
        message_bytes = message_json.encode('utf-8')
        header = len(message_bytes).to_bytes(4, 'big')
        client_socket.sendall(header + message_bytes)
        return True
    except (ConnectionResetError, ConnectionAbortedError):
        return False
    except Exception as e:
        print(f"[ERROR] メッセージの送信に失敗しました: {e}")
        return False
# =================================================================

def call_gemini_api(history, user_prompt):
    """[機能追加] ユーザー指定のプロンプトを受け取るように変更"""
    if not GEMINI_API_KEY: return "AI機能が設定されていません。"
    
    # 履歴からテキストメッセージのみを抽出（画像は含めない）
    prompt_history_list = []
    # 直近のテキストメッセージ10件を参考にする
    for msg in filter(lambda m: "message" in m and m.get("message"), history[-20:]):
        if len(prompt_history_list) >= 10: break
        prompt_history_list.append(f"{msg.get('username', 'Unknown')}: {msg['message']}")
    
    prompt_history = "\n".join(reversed(prompt_history_list)) # 新しい順にする

    # ユーザープロンプトと履歴を組み合わせて最終的なプロンプトを作成
    final_prompt = (
        "あなたはチャットを支援する、賢くてフレンドリーなAIアシスタントです。\n"
        "以下のチャット履歴とユーザーからの指示を考慮して、回答を生成してください。\n"
        "チャットの参加者のように、自然な言葉で応答してください。\n\n"
        "--- 直近のチャット履歴 ---\n"
        f"{prompt_history}\n"
        "--- ここまで ---\n\n"
        "--- ユーザーからの指示 ---\n"
        f"{user_prompt}\n"
        "--- ここまで ---\n\n"
        "AIアシスタントとしてのあなたの回答:"
    )

    try:
        response = model.generate_content(final_prompt)
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
            json.dump(board_messages, f, indent=2, ensure_ascii=False) # indentを2に変更
    except IOError: pass

def broadcast_board_info():
    message_to_send = {"command": "BoardInfo", "payload": board_messages}
    for client_socket in list(clients):
        if not send_message(client_socket, message_to_send):
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
        broadcast_board_info()

def handle_client(client_socket, addr):
    print(f"[INFO] {addr} から新しい接続がありました。")
    username = ""
    try:
        send_message(client_socket, {"command": "ConnectionStart"})
        
        while True:
            msg = receive_message(client_socket)
            if msg is None: break
            
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
            
            elif command == "SendImage": # [新機能] 画像メッセージの処理
                print(f"[IMAGE] {username} が画像を送信しました。")
                message = {"username": username, "image_data": payload, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                board_messages.append(message)
                save_chat_log()
                broadcast_board_info()

            elif command == "AI_HELP": # [機能追加] プロンプトを受け取る
                print(f"[AI] {username} がAIを呼び出しました。プロンプト: '{payload}'")
                ai_response = call_gemini_api(board_messages, user_prompt=payload)
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