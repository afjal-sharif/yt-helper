from .config_manager import ConfigManager
from .encoder_manager import EncoderManager

class StreamManager:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.config_manager = ConfigManager()
        self.encoder = None
        
    def get_config(self):
        return self.config_manager.config
        
    def update_config(self, config_data):
        return self.config_manager.save(config_data)
        
    def start_stream(self):
        if self.encoder and self.encoder.running:
            return False, "Already streaming"
            
        self.encoder = EncoderManager(self.config_manager.config)
        try:
            self.encoder.start()
            return True, "Stream started successfully"
        except Exception as e:
            return False, str(e)
            
    def stop_stream(self):
        if self.encoder and self.encoder.running:
            self.encoder.stop()
            return True, "Stream stopped"
        return False, "Not streaming"
        
    def get_status(self):
        if self.encoder:
            return self.encoder.stats
        return {
            "status": "stopped",
            "fps": 0,
            "bitrate": "0k",
            "uptime": "00:00:00",
            "stream_id": ""
        }
