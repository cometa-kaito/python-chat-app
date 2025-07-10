document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById('chat-box');
    const msgInput = document.getElementById('msg-input');
    const sendBtn = document.getElementById('send-btn');
    const imageInput = document.getElementById('image-input-hidden');
    const aiBtn = document.getElementById('ai-btn');

    let username = "";
    // WebSocketサーバーに接続
    const socket = new WebSocket('ws://10.101.223.218:8765');

    // 接続が開いたとき
    socket.onopen = () => {
        console.log("サーバーに接続しました。");
        username = prompt("ユーザー名を入力してください:", "Anonymous");
        if (!username) username = "Anonymous";
        // サーバーにユーザー名を送信
        socket.send(JSON.stringify({ command: "UserName", payload: username }));
    };

    // サーバーからメッセージを受信したとき
    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.command === "BoardInfo") {
            renderChatHistory(data.payload);
        }
    };

    // 接続が閉じたとき
    socket.onclose = () => {
        console.log("サーバーから切断されました。");
        addMessage({ username: "Server", message: "サーバーとの接続が切れました。" });
    };

    // メッセージをレンダリングする関数
    const renderChatHistory = (messages) => {
        chatBox.innerHTML = ''; // チャットボックスをクリア
        messages.forEach(addMessage);
    };

    // 1件のメッセージをチャットボックスに追加する関数
    const addMessage = (msg) => {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message';

        let tag = 'other';
        if (msg.username === username) tag = 'me';
        else if (msg.username === 'Server') tag = 'server';
        else if (msg.username === 'AI Assistant') tag = 'ai';
        msgDiv.classList.add(tag);

        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';
        
        const bodyDiv = document.createElement('div');
        bodyDiv.className = 'message-body';

        if (msg.image_data) {
            // 画像メッセージ
            const img = document.createElement('img');
            img.src = `data:image/png;base64,${msg.image_data}`;
            bodyDiv.appendChild(img);
        } else {
            // テキストメッセージ
            bodyDiv.textContent = msg.message;
        }

        const metaDiv = document.createElement('div');
        metaDiv.className = 'meta';
        const displayName = (tag === 'me' || tag === 'server') ? '' : msg.username;
        const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : '';
        metaDiv.textContent = `${displayName} ${timestamp}`.trim();

        contentDiv.appendChild(bodyDiv);
        msgDiv.appendChild(contentDiv);
        msgDiv.appendChild(metaDiv);
        chatBox.appendChild(msgDiv);

        chatBox.scrollTop = chatBox.scrollHeight; // 自動スクロール
    };

    // テキストメッセージを送信
    const sendTextMessage = () => {
        const message = msgInput.value;
        if (message.trim() !== "") {
            socket.send(JSON.stringify({ command: "Send", payload: message }));
            msgInput.value = '';
        }
    };

    // 画像を送信
    imageInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                socket.send(JSON.stringify({ command: "SendImage", payload: e.target.result }));
            };
            reader.readAsDataURL(file); // Base64形式で読み込む
        }
    });

    // AIヘルプをリクエスト
    aiBtn.addEventListener('click', () => {
        const promptText = prompt("AIへの指示や質問を入力してください:");
        if (promptText) {
            socket.send(JSON.stringify({ command: "AI_HELP", payload: promptText }));
        }
    });

    sendBtn.addEventListener('click', sendTextMessage);
    msgInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendTextMessage();
    });
});
