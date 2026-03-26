import requests
import os


def send_wecom_message(content: str):
    """
    使用企业微信 Webhook 发送 Markdown 消息到群聊
    """
    webhook_key = os.environ.get('WECOM_WEBHOOK_KEY')
    
    if not webhook_key:
        raise Exception("环境变量 WECOM_WEBHOOK_KEY 未设置，请在 GitHub Secrets 中配置")
    
    # 检查 Key 格式
    if 'http' in webhook_key or len(webhook_key) < 30:
        raise Exception("Key 格式错误：请不要包含 URL，只保留 key= 后面的部分")
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }
    
    print(f"   发送 Webhook 请求...")
    response = requests.post(url, json=payload, timeout=10)
    result = response.json()
    
    if result.get("errcode") != 0:
        raise Exception(f"企业微信返回错误: {result.get('errmsg')} (errcode: {result.get('errcode')})")
    
    print(f"   ✅ Webhook 推送成功")
    return result
