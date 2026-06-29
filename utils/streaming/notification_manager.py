import requests

class NotificationManager:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
    
    def send(self, msg):
        if not self.bot_token or not self.chat_id:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data={
                    "chat_id": self.chat_id,
                    "text": msg
                },
                timeout=5
            )
        except Exception as e:
            print(f"Telegram notification failed: {e}")
