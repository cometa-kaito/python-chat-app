import socket
import threading
import json
from datetime import datetime

# --- 設定 ---
HOST = '127.0.0.1'
PORT = 12345
# ---

clients = []
client_info = {}
board_messages = []

def broadcast(message_data):
    message_json = json.dumps(message_data)
    for client_socket in clients:
        try:
            client_socket.sendall(f"BoardInfo:{message_json}".encode('utf-8'))
        except socket.error:
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
        board_messages.append({
            "username": "Server",
            "message": f"{user_to_remove} が退出しました。",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        broadcast(board_messages)

def handle_client(client_socket, addr):
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
                board_messages.append({
                    "username": "Server",
                    "message": f"{username} が参加しました。",
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                broadcast(board_messages)
            elif command == "Send":
                print(f"[MESSAGE] {username}: {payload}")
                message = {
                    "username": username,
                    "message": payload,
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                board_messages.append(message)
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
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
        
        # 接続の待ち行列サイズを10に指定
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
        for client in clients:
            client.close()
        server_socket.close()

if __name__ == "__main__":
    main()