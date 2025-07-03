import asyncio
import websockets
import json
from datetime import datetime
import os
import google.generativeai as genai
import base64

# --- 設定 (変更なし) ---
HOST = '0.0.0.0'
PORT = 8765
CHAT_LOG_FILE = "chat_log.json"

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

# --- WebSocket用のグローバル変数 ---
CONNECTED_CLIENTS = set()
board_messages = []

# --- チャットロジック (変更なし) ---
def call_gemini_api(history, user_prompt):
    if not GEMINI_API_KEY: return "AI機能が設定されていません。"
    prompt_history_list = []
    for msg in filter(lambda m: "message" in m and m.get("message"), history[-20:]):
        if len(prompt_history_list) >= 10: break
        prompt_history_list.append(f"{msg.get('username', 'Unknown')}: {msg['message']}")
    prompt_history = "\n".join(reversed(prompt_history_list))
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
            json.dump(board_messages, f, indent=2, ensure_ascii=False)
    except IOError: pass

# --- WebSocket用の通信関数 ---
async def broadcast_board_info():
    """全クライアントに最新の掲示板情報をブロードキャストする"""
    if CONNECTED_CLIENTS:
        message_to_send = json.dumps({"command": "BoardInfo", "payload": board_messages})
        # ★★★ ここを修正 ★★★
        # asyncio.waitからasyncio.gatherに変更して、複数の非同期処理を同時に実行
        await asyncio.gather(*[client.send(message_to_send) for client in CONNECTED_CLIENTS])

# --- メインのクライアント処理 ---
async def handle_client(websocket):
    """クライアントからの接続とメッセージを処理する"""
    CONNECTED_CLIENTS.add(websocket)
    username = "Anonymous"
    try:
        print(f"[INFO] 新しいクライアントが接続しました: {websocket.remote_address}")
        await broadcast_board_info()

        async for message in websocket:
            data = json.loads(message)
            command = data.get("command")
            payload = data.get("payload")

            if command == "UserName":
                username = payload
                print(f"[INFO] ユーザー名を設定: {username}")
                server_msg = {"username": "Server", "message": f"{username} が参加しました。", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                board_messages.append(server_msg)

            elif command == "Send":
                print(f"[MESSAGE] {username}: {payload}")
                msg_data = {"username": username, "message": payload, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                board_messages.append(msg_data)

            elif command == "SendImage":
                print(f"[IMAGE] {username} が画像を送信しました。")
                img_data_b64 = payload.split(',')[1]
                msg_data = {"username": username, "image_data": img_data_b64, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                board_messages.append(msg_data)

            elif command == "AI_HELP":
                print(f"[AI] {username} がAIを呼び出しました。プロンプト: '{payload}'")
                ai_response = call_gemini_api(board_messages, user_prompt=payload)
                ai_message = {"username": "AI Assistant", "message": ai_response, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                board_messages.append(ai_message)

            save_chat_log()
            await broadcast_board_info()

    except websockets.exceptions.ConnectionClosed:
        print(f"[INFO] クライアントが切断されました: {websocket.remote_address}")
    finally:
        # クライアントが切断した場合の処理
        if websocket in CONNECTED_CLIENTS:
            CONNECTED_CLIENTS.remove(websocket)
        server_msg = {"username": "Server", "message": f"{username} が退出しました。", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        board_messages.append(server_msg)
        save_chat_log()
        await broadcast_board_info()

async def main():
    """サーバーを起動する"""
    global board_messages
    board_messages = load_chat_log()
    print(f"[INFO] 過去のチャットログを {len(board_messages)} 件読み込みました。")

    async with websockets.serve(handle_client, HOST, PORT):
        print(f"[INFO] サーバーが ws://{HOST}:{PORT} で起動しました。")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] サーバーを停止します。")