import socket
import threading
import json
from datetime import datetime
import os # ファイル操作のためにosモジュールをインポート

# --- 設定 ---
HOST = '127.0.0.1'
PORT = 12345
CHAT_LOG_FILE = "chat_log.json" # ログファイル名
# ---

# 接続中のクライアントソケットを管理するリスト
clients = []
# ユーザー名とソケットを対応付ける辞書
client_info = {}
# チャット履歴を保持するリスト（起動時にファイルから読み込む）
board_messages = []


def load_chat_log():
    """
    起動時にチャットログファイルを読み込む
    """
    if not os.path.exists(CHAT_LOG_FILE):
        return [] # ファイルがなければ空のリストを返す
    
    try:
        with open(CHAT_LOG_FILE, 'r', encoding='utf-8') as f:
            # ファイルが空の場合の対策
            content = f.read()
            if not content:
                return []
            return json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[WARNING] ログファイルの読み込みに失敗しました: {e}")
        return []

def save_chat_log():
    """
    チャット履歴をJSONファイルに保存する
    """
    try:
        with open(CHAT_LOG_FILE, 'w', encoding='utf-8') as f:
            # indent=4 で整形、ensure_ascii=False で日本語をそのまま保存
            json.dump(board_messages, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"[ERROR] ログファイルの保存に失敗しました: {e}")


def broadcast(message_data):
    """
    接続している全てのクライアントにメッセージを送信する
    """
    message_json = json.dumps(message_data)
    for client_socket in clients:
        try:
            client_socket.sendall(f"BoardInfo:{message_json}".encode('utf-8'))
        except socket.error:
            remove_client(client_socket)

def remove_client(client_socket):
    """
    クライアントを切断リストから削除する
    """
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
        board_messages.append({
            "username": "Server",
            "message": f"{user_to_remove} が退出しました。",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_chat_log() # ログを保存
        broadcast(board_messages)


def handle_client(client_socket, addr):
    """
    個々のクライアントとの通信を処理するスレッド
    """
    print(f"[INFO] {addr} から新しい接続がありました。")
    username = ""
    try:
        client_socket.sendall("Connection Start:".encode('utf-8'))
        while True:
            data = client_socket.recv(1024).decode('utf-8')
            if not data:
                break
            parts = data.split(':', 1)
            command = parts[0]
            payload = parts[1] if len(parts) > 1 else ""

            if command == "UserName":
                username = payload
                client_info[username] = client_socket
                print(f"[INFO] {addr} のユーザー名は {username} です。")
                client_socket.sendall(f"NameRecieved:{username}".encode('utf-8'))
                
                # 過去ログも含めて送信するため、参加メッセージを追加してからブロードキャスト
                board_messages.append({
                    "username": "Server",
                    "message": f"{username} が参加しました。",
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                save_chat_log() # ログを保存
                broadcast(board_messages)

            elif command == "Send":
                print(f"[MESSAGE] {username}: {payload}")
                message = {
                    "username": username,
                    "message": payload,
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                board_messages.append(message)
                save_chat_log() # ログを保存
                broadcast(board_messages)
            
            elif command == "End":
                print(f"[INFO] {username} が正常に接続を終了しました。")
                break
    except ConnectionResetError:
        print(f"[ERROR] {addr} との接続がリセットされました。")
    except Exception as e:
        print(f"[ERROR] {addr} との通信でエラーが発生しました: {e}")
    finally:
        remove_client(client_socket)
        client_socket.close()


def main():
    global board_messages
    # 起動時にグローバル変数のboard_messagesをファイルから読み込んだ内容で初期化
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
        # 念のため、終了時にもログを保存する
        print("[INFO] 最終的なチャットログを保存しています...")
        save_chat_log()
        for client in clients:
            client.close()
        server_socket.close()

if __name__ == "__main__":
    main()