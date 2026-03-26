import json
import websocket
import ssl
import time
import os
from typing import Optional

class WeComBot:
    WSS_URL = "wss://openws.work.weixin.qq.com"
    
    def __init__(self, bot_id: str, secret: str, recv_id: str):
        self.bot_id = bot_id
        self.secret = secret
        self.recv_id = recv_id
        self.ws: Optional[websocket.WebSocket] = None
        
    def _connect(self):
        """建立 WebSocket 长连接"""
        try:
            print(f"   🔌 连接 WebSocket: {self.WSS_URL}")
            self.ws = websocket.create_connection(
                self.WSS_URL,
                sslopt={"cert_reqs": ssl.CERT_NONE},
                timeout=10
            )
            print("   ✅ WebSocket 连接成功")
        except Exception as e:
            raise Exception(f"WebSocket 连接失败: {e}")
        
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
        
        try:
            self.ws.send(json.dumps(subscribe_cmd))
            print("   📤 订阅请求已发送")
            
            response = json.loads(self.ws.recv())
            print(f"   📥 订阅响应: {response}")
            
            if response.get("errcode") != 0:
                raise Exception(f"订阅失败: {response.get('errmsg')} (errcode: {response.get('errcode')})")
            
            print("   ✅ 订阅成功")
            return True
        except websocket.WebSocketTimeoutException:
            raise Exception("订阅超时：请检查 Bot ID 和 Secret 是否正确")
        except Exception as e:
            raise Exception(f"订阅过程错误: {e}")
    
    def send_text_message(self, content: str) -> dict:
        """发送文本消息"""
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
                    "msgtype": "text",
                    "text": {
                        "content": content
                    }
                }
            }
            
            print(f"   📤 发送消息给: {self.recv_id}")
            self.ws.send(json.dumps(send_cmd))
            
            response = json.loads(self.ws.recv())
            print(f"   📥 发送响应: {response}")
            
            if response.get("errcode") != 0:
                raise Exception(f"发送消息失败: {response.get('errmsg')} (errcode: {response.get('errcode')})")
            
            return response
            
        except Exception as e:
            raise Exception(f"发送消息时出错: {e}")
        finally:
            if self.ws:
                self.ws.close()
                print("   🔌 连接已关闭")
    
    def send_markdown_message(self, content: str) -> dict:
        """发送 Markdown 格式消息"""
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
