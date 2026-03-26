import json
import requests
import os
import sys
import traceback
from datetime import datetime
from rapidfuzz import fuzz

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# 配置路径（改用 YAML）
OPEN_SANCTIONS_URL = "https://data.opensanctions.org/datasets/us_ofac_sdn/targets.simple.csv"
STATE_FILE = os.path.join(ROOT_DIR, "data", "last_check.json")
CONFIG_FILE = os.path.join(ROOT_DIR, "config", "watchlist.yaml")  # 改为 .yaml

def load_config():
    """加载 YAML 配置"""
    import yaml
    
    print(f"   正在加载配置: {CONFIG_FILE}")
    print(f"   工作目录: {os.getcwd()}")
    print(f"   检查路径是否存在: {os.path.exists(CONFIG_FILE)}")
    
    # 列出 config 目录内容帮助调试
    config_dir = os.path.join(ROOT_DIR, "config")
    if os.path.exists(config_dir):
        print(f"   config 目录内容: {os.listdir(config_dir)}")
    else:
        print(f"   config 目录不存在！创建中...")
        os.makedirs(config_dir, exist_ok=True)
    
    if not os.path.exists(CONFIG_FILE):
        print(f"   错误：找不到 {CONFIG_FILE}")
        sys.exit(1)
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print(f"   ✅ 配置加载成功，监测 {len(config.get('companies', []))} 家公司")
        return config
    except Exception as e:
        print(f"错误：无法解析 YAML: {e}")
        sys.exit(1)

def load_last_state():
    """加载上次检查状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"警告：读取状态失败: {e}")
    return {"last_check": None, "matched_entities": []}

def save_state(state):
    """保存状态"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"✅ 状态已保存")
    except Exception as e:
        print(f"警告：保存状态失败: {e}")

def fetch_sdn_list():
    """获取 SDN 清单"""
    try:
        response = requests.get(OPEN_SANCTIONS_URL, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ 获取 SDN 数据失败: {e}")
        return None

def parse_sdn_data(csv_text):
    """解析 CSV"""
    lines = csv_text.strip().split('\n')
    entities = []
    for line in lines[1:]:
        values = line.split(',')
        if len(values) >= 3:
            entities.append({
                'name': values[0].strip('"'),
                'type': values[1].strip('"'),
                'programs': values[2].strip('"')
            })
    return entities

def check_matches(entities, watchlist):
    """模糊匹配"""
    matches = []
    for entity in entities:
        for company in watchlist['companies']:
            candidates = [company['name']] + company.get('aliases', [])
            for candidate in candidates:
                score = fuzz.token_set_ratio(candidate, entity['name'])
                threshold = company.get('confidence_threshold', 0.8) * 100
                if score >= threshold and score >= watchlist.get('min_match_score', 75):
                    matches.append({
                        'watch_name': company['name'],
                        'matched_name': entity['name'],
                        'type': entity['type'],
                        'programs': entity['programs'],
                        'score': round(score, 1)
                    })
                    break
    return matches

def main():
    print(f"🚀 SDN 监测开始 - {datetime.now()}")
    
    # 1. 加载配置
    print("步骤 1: 加载配置...")
    config = load_config()
    
    # 2. 获取数据
    print("步骤 2: 获取 SDN 数据...")
    sdn_data = fetch_sdn_list()
    if not sdn_data:
        sys.exit(1)
    
    entities = parse_sdn_data(sdn_data)
    print(f"   解析到 {len(entities)} 个实体")
    
    # 3. 匹配检查
    print("步骤 3: 匹配检查...")
    current_matches = check_matches(entities, config)
    print(f"   发现 {len(current_matches)} 个匹配")
    
    # 4. 检查新增
    last_state = load_last_state()
    prev_names = {m['matched_name'] for m in last_state.get('matched_entities', [])}
    new_matches = [m for m in current_matches if m['matched_name'] not in prev_names]
    
    if new_matches:
        print(f"   🆕 新增 {len(new_matches)} 个命中: {[m['matched_name'] for m in new_matches]}")
    
    # 5. 发送通知
    if new_matches or config.get('alert_on_update'):
        print("步骤 4: 发送企业微信通知...")
        try:
            from wecom_bot import WeComBot
            bot = WeComBot(
                os.environ['WECOM_BOT_ID'],
                os.environ['WECOM_SECRET'],
                os.environ['WECOM_RECV_ID']
            )
            
            msg = f"🚨 SDN 监测告警\n\n"
            if new_matches:
                msg += f"新增命中 {len(new_matches)} 个：\n"
                for m in new_matches:
                    msg += f"• {m['watch_name']} → {m['matched_name']} ({m['score']}%)\n"
            else:
                msg += "数据已更新，无新增命中"
            
            bot.send_text_message(msg)
            print("   ✅ 推送成功")
        except Exception as e:
            print(f"   ❌ 推送失败: {e}")
    
    # 6. 保存状态
    save_state({
        "last_check": datetime.now().isoformat(),
        "entity_count": len(entities),
        "matched_entities": current_matches
    })
    
    print("✅ 监测完成")

if __name__ == "__main__":
    main()
