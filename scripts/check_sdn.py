import json
import requests
import os
import sys
from datetime import datetime
from fuzzywuzzy import fuzz
from wecom_bot import WeComBot

# 配置
OPEN_SANCTIONS_URL = "https://data.opensanctions.org/datasets/us_ofac_sdn/targets.simple.csv"
STATE_FILE = "data/last_check.json"
CONFIG_FILE = "config/watchlist.json"

def load_config():
    """加载监测配置"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_last_state():
    """加载上次检查状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"last_check": None, "matched_entities": []}

def save_state(state):
    """保存当前状态"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_sdn_list():
    """获取最新 SDN 清单"""
    try:
        response = requests.get(OPEN_SANCTIONS_URL, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching SDN list: {e}")
        return None

def parse_sdn_data(csv_text):
    """解析 CSV 数据"""
    lines = csv_text.strip().split('\n')
    headers = lines[0].split(',')
    entities = []
    
    for line in lines[1:]:
        values = line.split(',')
        if len(values) >= 3:
            entities.append({
                'name': values[0].strip('"'),
                'type': values[1].strip('"') if len(values) > 1 else '',
                'programs': values[2].strip('"') if len(values) > 2 else ''
            })
    return entities

def check_matches(entities, watchlist):
    """模糊匹配检查"""
    matches = []
    thresholds = {c['name']: c.get('confidence_threshold', 0.80) * 100 
                  for c in watchlist['companies']}
    
    for entity in entities:
        for company in watchlist['companies']:
            # 多维度匹配：正式名称 + 别名
            candidates = [company['name']] + company.get('aliases', [])
            entity_name = entity['name']
            
            for candidate in candidates:
                # 使用 token_set_ratio 处理变体和缩写
                score = fuzz.token_set_ratio(candidate.lower(), entity_name.lower())
                min_score = company.get('confidence_threshold', 0.80) * 100
                
                if score >= min_score and score >= watchlist['min_match_score']:
                    matches.append({
                        'watch_name': company['name'],
                        'matched_name': entity_name,
                        'type': entity['type'],
                        'programs': entity['programs'],
                        'score': score,
                        'timestamp': datetime.now().isoformat()
                    })
                    break  # 该公司已匹配，跳过后续别名检查
    return matches

def format_alert_message(matches, is_update=False):
    """格式化告警消息"""
    msg = "🚨 SDN 制裁清单监测告警\n\n"
    
    if is_update:
        msg += "📊 清单状态：数据已更新\n"
    
    if matches:
        msg += f"⚠️ 发现 {len(matches)} 个匹配项：\n\n"
        for idx, match in enumerate(matches, 1):
            msg += f"{idx}. {match['watch_name']} → 匹配到「{match['matched_name']}」\n"
            msg += f"   类型：{match['type']} | 制裁项目：{match['programs']}\n"
            msg += f"   匹配度：{match['score']}%\n\n"
    else:
        msg += "✅ 本次检查未发现名单内公司被列入 SDN 清单\n"
    
    msg += f"\n⏰ 检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    msg += "\n📋 数据来源：US OFAC SDN List (via OpenSanctions)"
    return msg

def main():
    # 1. 加载配置
    config = load_config()
    last_state = load_last_state()
    
    # 2. 获取最新 SDN 数据
    print("Fetching latest SDN list...")
    snd_data = fetch_sdn_list()
    if not snd_data:
        sys.exit(1)
    
    # 3. 解析数据
    entities = parse_sdn_data(snd_data)
    print(f"Loaded {len(entities)} entities from SDN list")
    
    # 4. 执行匹配检查
    current_matches = check_matches(entities, config)
    print(f"Found {len(current_matches)} matches")
    
    # 5. 检测新增匹配（对比上次结果）
    prev_matched_names = {m['matched_name'] for m in last_state.get('matched_entities', [])}
    new_matches = [m for m in current_matches if m['matched_name'] not in prev_matched_names]
    
    # 6. 判断是否需要发送告警
    should_alert = False
    alert_reason = []
    
    if new_matches:
        should_alert = True
        alert_reason.append(f"新增 {len(new_matches)} 个匹配")
    
    if config.get('alert_on_update') and last_state.get('last_check'):
        # 简单通过数据长度或哈希判断是否更新（实际可对比时间戳）
        should_alert = True
        alert_reason.append("清单数据更新")
    
    # 7. 发送企业微信通知
    if should_alert:
        bot = WeComBot(
            bot_id=os.environ['WECOM_BOT_ID'],
            secret=os.environ['WECOM_SECRET'],
            recv_id=os.environ['WECOM_RECV_ID']
        )
        
        message = format_alert_message(current_matches, is_update=config.get('alert_on_update'))
        if new_matches:
            message += f"\n\n🆕 新增命中：{[m['matched_name'] for m in new_matches]}"
        
        try:
            result = bot.send_text_message(message)
            print(f"WeCom push result: {result}")
        except Exception as e:
            print(f"Failed to send WeCom message: {e}")
            sys.exit(1)
    
    # 8. 保存状态
    save_state({
        "last_check": datetime.now().isoformat(),
        "entity_count": len(entities),
        "matched_entities": current_matches
    })
    
    print("Check completed successfully")

if __name__ == "__main__":
    main()
