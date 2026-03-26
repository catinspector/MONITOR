import json
import requests
import os
import sys
import traceback
from datetime import datetime
from rapidfuzz import fuzz

# 获取脚本所在目录，确保文件路径正确
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# 配置（使用绝对路径）
OPEN_SANCTIONS_URL = "https://data.opensanctions.org/datasets/us_ofac_sdn/targets.simple.csv"
STATE_FILE = os.path.join(ROOT_DIR, "data", "last_check.json")
CONFIG_FILE = os.path.join(ROOT_DIR, "config", "watchlist.json")

def load_config():
    """加载 JSON 配置"""
    print(f"   正在加载配置: {CONFIG_FILE}")
    print(f"   工作目录: {os.getcwd()}")
    print(f"   脚本目录: {SCRIPT_DIR}")
    print(f"   根目录: {ROOT_DIR}")
    
    # 检查文件是否存在
    if not os.path.exists(CONFIG_FILE):
        print(f"   错误：文件不存在！")
        # 列出 config 目录内容（如果存在）
        config_dir = os.path.dirname(CONFIG_FILE)
        if os.path.exists(config_dir):
            print(f"   目录 {config_dir} 内容: {os.listdir(config_dir)}")
        else:
            print(f"   目录 {config_dir} 不存在！")
        sys.exit(1)
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"   ✅ 配置加载成功，监测 {len(config.get('companies', []))} 家公司")
        return config
    except json.JSONDecodeError as e:
        print(f"   错误：JSON 格式错误（检查是否有注释或尾随逗号）: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"   错误：无法加载配置: {e}")
        sys.exit(1)

def load_last_state():
    """加载上次检查状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"   警告：读取状态文件失败: {e}，将创建新状态")
    return {"last_check": None, "matched_entities": []}

def save_state(state):
    """保存当前状态"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"   状态已保存到 {STATE_FILE}")
    except Exception as e:
        print(f"   警告：保存状态失败: {e}")

def fetch_sdn_list():
    """获取最新 SDN 清单"""
    print("步骤 2: 获取 SDN 数据...")
    try:
        response = requests.get(OPEN_SANCTIONS_URL, timeout=30)
        response.raise_for_status()
        print(f"   成功获取数据，大小: {len(response.text)} 字符")
        return response.text
    except Exception as e:
        print(f"   错误：获取 SDN 列表失败: {e}")
        return None

def parse_sdn_data(csv_text):
    """解析 CSV 数据"""
    try:
        lines = csv_text.strip().split('\n')
        if len(lines) < 2:
            print("   警告：CSV 数据为空或格式异常")
            return []
            
        entities = []
        
        for line in lines[1:]:
            values = line.split(',')
            if len(values) >= 3:
                entities.append({
                    'name': values[0].strip('"'),
                    'type': values[1].strip('"') if len(values) > 1 else '',
                    'programs': values[2].strip('"') if len(values) > 2 else ''
                })
        
        print(f"   解析完成：共 {len(entities)} 个实体")
        return entities
    except Exception as e:
        print(f"   CSV 解析错误: {e}")
        return []

def check_matches(entities, watchlist):
    """模糊匹配检查"""
    print("步骤 3: 匹配检查...")
    matches = []
    
    for entity in entities:
        for company in watchlist['companies']:
            candidates = [company['name']] + company.get('aliases', [])
            entity_name = entity['name']
            
            for candidate in candidates:
                score = fuzz.token_set_ratio(candidate, entity_name)
                min_score = company.get('confidence_threshold', 0.80) * 100
                
                if score >= min_score and score >= watchlist.get('min_match_score', 75):
                    matches.append({
                        'watch_name': company['name'],
                        'matched_name': entity_name,
                        'type': entity['type'],
                        'programs': entity['programs'],
                        'score': round(score, 1),
                        'timestamp': datetime.now().isoformat()
                    })
                    break
    
    print(f"   发现 {len(matches)} 个匹配项")
    return matches

def format_alert_message(matches, new_matches, is_update=False):
    """格式化告警消息"""
    msg = "🚨 SDN 制裁清单监测告警\n\n"
    
    if is_update:
        msg += "📊 清单状态：数据已更新\n\n"
    
    if new_matches:
        msg += f"🆕 新增命中 {len(new_matches)} 个：\n"
        for idx, match in enumerate(new_matches, 1):
            msg += f"{idx}. {match['watch_name']} → 「{match['matched_name']}」\n"
            msg += f"   类型：{match['type']} | 制裁项目：{match['programs']}\n"
            msg += f"   匹配度：{match['score']}%\n\n"
    
    if matches:
        msg += f"📋 当前共 {len(matches)} 个监测命中（含历史）\n"
    else:
        msg += "✅ 当前无监测命中\n"
    
    msg += f"\n⏰ 检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    msg += "\n📋 数据来源：US OFAC SDN List (via OpenSanctions)"
    return msg

def main():
    print(f"🚀 SDN 监测任务开始 - {datetime.now()}")
    print("=" * 50)
    
    try:
        # 1. 加载配置
        print("步骤 1: 加载配置...")
        config = load_config()
        
        # 2. 获取数据
        sdn_data = fetch_sdn_list()
        if not sdn_data:
            sys.exit(1)
        
        entities = parse_sdn_data(sdn_data)
        if not entities:
            print("错误：未解析到实体数据")
            sys.exit(1)
        
        # 3. 匹配检查
        current_matches = check_matches(entities, config)
        
        # 4. 检测新增
        print("步骤 4: 检测新增...")
        last_state = load_last_state()
        prev_matched_names = {m['matched_name'] for m in last_state.get('matched_entities', [])}
        new_matches = [m for m in current_matches if m['matched_name'] not in prev_matched_names]
        
        if new_matches:
            print(f"   🆕 新增命中：{[m['matched_name'] for m in new_matches]}")
        else:
            print(f"   无新增命中")
        
        # 5. 判断是否推送
        should_alert = bool(new_matches) or config.get('alert_on_update', False)
        
        if should_alert:
            print("步骤 5: 发送企业微信通知...")
            
            try:
                from wecom_bot import WeComBot
            except ImportError as e:
                print(f"   错误：导入 WeComBot 失败: {e}")
                sys.exit(1)
            
            bot_id = os.environ.get('WECOM_BOT_ID')
            secret = os.environ.get('WECOM_SECRET')
            recv_id = os.environ.get('WECOM_RECV_ID')
            
            if not all([bot_id, secret, recv_id]):
                print(f"   错误：环境变量缺失")
                print(f"   WECOM_BOT_ID: {'已设置' if bot_id else '缺失'}")
                print(f"   WECOM_SECRET: {'已设置' if secret else '缺失'}")
                print(f"   WECOM_RECV_ID: {'已设置' if recv_id else '缺失'}")
                sys.exit(1)
            
            try:
                bot = WeComBot(bot_id=bot_id, secret=secret, recv_id=recv_id)
                message = format_alert_message(current_matches, new_matches, is_update=config.get('alert_on_update'))
                
                result = bot.send_text_message(message)
                print(f"   ✅ 推送成功")
            except Exception as e:
                print(f"   ❌ 推送失败: {e}")
                traceback.print_exc()
        else:
            print("步骤 5: 无需推送（无新增命中）")
        
        # 6. 保存状态
        print("步骤 6: 保存状态...")
        state_data = {
            "last_check": datetime.now().isoformat(),
            "entity_count": len(entities),
            "matched_entities": current_matches
        }
        save_state(state_data)
        
        print("=" * 50)
        print("✅ 监测任务完成")
        
    except Exception as e:
        print(f"❌ 任务执行失败: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
