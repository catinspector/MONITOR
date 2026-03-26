import requests
import os


def send_wecom_message(content: str):
    """
    使用企业微信 Webhook 发送 Markdown 消息到群聊
    无需公网 IP，HTTP POST 直接推送
    """
    webhook_key = os.environ.get('WECOM_WEBHOOK_KEY')
    
    if not webhook_key:
        raise Exception("环境变量 WECOM_WEBHOOK_KEY 未设置，请在 GitHub Secrets 中配置")
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }
    
    print(f"   发送 Webhook 请求到企业微信...")
    response = requests.post(url, json=payload, timeout=10)
    result = response.json()
    
    if result.get("errcode") != 0:
        raise Exception(f"企业微信返回错误: {result.get('errmsg')} (errcode: {result.get('errcode')})")
    
    print(f"   ✅ Webhook 推送成功")
    return result


def send_text_message(content: str):
    """
    发送纯文本消息（备用）
    """
    webhook_key = os.environ.get('WECOM_WEBHOOK_KEY')
    
    if not webhook_key:
        raise Exception("环境变量 WECOM_WEBHOOK_KEY 未设置")
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    
    # 截断过长消息
    if len(content) > 4000:
        content = content[:3997] + "..."
    
    payload = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }
    
    response = requests.post(url, json=payload, timeout=10)
    result = response.json()
    
    if result.get("errcode") != 0:
        raise Exception(f"发送失败: {result.get('errmsg')}")
    
    return result
