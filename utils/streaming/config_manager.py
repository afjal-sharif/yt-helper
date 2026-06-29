import json
import os

CONFIG_FILE = "stream_config.json"

class ConfigManager:
    def __init__(self):
        self.config = self.load()
    
    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return self.default_config()

    def save(self, config_data):
        self.config.update(config_data)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)
        return self.config

    def default_config(self):
        return {
            "channel_name": "My Channel",
            "company_name": "My Company",
            "bot_token": "",
            "chat_id": "",
            "video_bitrate": "5000k",
            "audio_bitrate": "128k",
            "fps": "30",
            "resolution": "1920x1080",
            "hw_accel": "none",
            "outputs": [],
            "source": "",
            "overlays": {
                "logo": False,
                "banner": False,
                "qr": False,
                "text": True,
                "timestamp": True,
                "watermark": True
            }
        }
