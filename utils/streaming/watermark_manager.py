import hashlib
import random
import string
import threading
import time
from datetime import datetime
import os
import qrcode

class WatermarkManager:
    def __init__(self, stream_id, source_url, channel_name):
        self.stream_id = stream_id
        seed = f"{stream_id}-{source_url}-{time.time()}"
        self.stream_sha = hashlib.sha256(seed.encode()).hexdigest()
        self.channel_name = channel_name
        self.running = False
        self.thread = None
        
        self.qr_path = "qr.png"
        self.forensic_path = "forensic.txt"
        
    def generate_qr(self):
        qr_text = f"Channel: {self.channel_name}\nStreamID: {self.stream_id}\nSHA256: {self.stream_sha}"
        qrcode.make(qr_text).save(self.qr_path)
        
    def start(self):
        self.generate_qr()
        self.running = True
        self.update_file("INITIAL")
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        
    def update_file(self, token):
        txt = (
            f"ID:{self.stream_id} | "
            f"TOKEN:{token} | "
            f"SHA:{self.stream_sha[:12]} | "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        with open(self.forensic_path, "w", encoding="utf-8") as f:
            f.write(txt)
            
    def _loop(self):
        while self.running:
            token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            self.update_file(token)
            for _ in range(300):
                if not self.running:
                    break
                time.sleep(1)
