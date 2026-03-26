import json
import websocket
import ssl
import time
from typing import Optional

class WeComBot:
    """企业微信长连接机器人客户端"""
    
    WSS_URL = "wss://openws.work.weixin.qq.com"
    
    def __init__(self, bot_id: str, secret: str, recv_id: str):
        self.bot_id = bot_id
        self.secret = secret
        self.recv_id = recv_id
        self.ws: Optional[websocket.WebSocket] = None
        
    def _connect(self):
        """建立 WebSocket 长连接"""
        # 禁用 SSL 验证（仅用于测试环境，生产环境建议保留证书验证）
        self.ws = websocket.create_connection(
            self.WSS_URL,
            sslopt={"cert_reqs": ssl.CERT_NONE} if ssl else {}
        )
        
    def _subscribe(self) -> bool:
        """发送订阅请求"""
        subscribe_cmd = {
            "cmd": "aibot_subscribe",
            "headers": {
                "req_id": f"sub_{int(time.time() * 1000)}"
            },
            "body": {
                "bot_id": self.bot_id,
                "secret": self.secret
            }
        }
        
        self.ws.send(json.dumps(subscribe_cmd))
        response = json.loads(self.ws.recv())
        
        if response.get("errcode") != 0:
            raise Exception(f"Subscription failed: {response.get('errmsg')}")
        
        print(f"Successfully subscribed to WeCom bot: {self.bot_id}")
        return True
    
    def send_text_message(self, content: str) -> dict:
        """发送文本消息"""
        try:
            self._connect()
            self._subscribe()
            
            # 构建主动推送消息命令
            # 注意：需要用户先与机器人有过会话，recv_id 才能生效
            send_cmd = {
                "cmd": "aibot_send_msg",
                "headers": {
                    "req_id": f"send_{int(time.time() * 1000)}"
                },
                "body": {
                    "recv_id": self.recv_id,  # 群聊ID或用户ID
                    "msgtype": "text",
                    "text": {
                        "content": content
                    }
                }
            }
            
            self.ws.send(json.dumps(send_cmd))
            response = json.loads(self.ws.recv())
            
            if response.get("errcode") != 0:
                raise Exception(f"Send message failed: {response.get('errmsg')}")
            
            return response
            
        finally:
            if self.ws:
                self.ws.close()
    
    def send_markdown_message(self, content: str) -> dict:
        """发送 Markdown 格式消息（支持更丰富的格式）"""
        try:
            self._connect()
            self._subscribe()
            
            send_cmd = {
                "cmd": "aibot_send_msg",
                "headers": {
                    "req_id": f"send_{int(time.time() * 1000)}"
                },
                "body": {
                    "recv_id": self.recv_id,
                    "msgtype": "markdown",
                    "markdown": {
                        "content": content
                    }
                }
            }
            
            self.ws.send(json.dumps(send_cmd))
            response = json.loads(self.ws.recv())
            return response
            
        finally:
            if self.ws:
                self.ws.close()
