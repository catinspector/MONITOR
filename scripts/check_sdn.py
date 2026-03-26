import json
import requests
import os
import sys
import traceback
from datetime import datetime
from rapidfuzz import fuzz  # 替代 fuzzywuzzy，纯 Python 实现

# 配置
OPEN_SANCTIONS_URL = "https://data.opensanctions.org/datasets/us_ofac_sdn/targets.simple.csv"
STATE_FILE = "data/last_check.json"
CONFIG_FILE = "config/watchlist.json"

def load_config():
    """加载监测配置"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 错误：无法加载配置文件 {CONFIG_FILE}: {e}")
        sys.exit(1)

def load_last_state():
    """加载上次检查状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 警告：读取状态文件失败: {e}，将创建新状态")
    return {"last_check": None, "matched_entities": []}

def save_state(state):
    """保存当前状态"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"✅ 状态已保存到 {STATE_FILE}")
    except Exception as e:
        print(f"⚠️ 警告：保存状态失败: {e}")

def fetch_sdn_list():
    """获取最新 SDN 清单"""
    print(f"🌐 正在获取 SDN 数据: {OPEN_SANCTIONS_URL}")
    try:
        response = requests.get(OPEN_SANCTIONS_URL, timeout=30)
        response.raise_for_status()
        print(f"✅ 成功获取数据，大小: {len(response.text)} 字符")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误：获取 SDN 列表失败: {e}")
        return None
    except Exception as e:
        print(f"❌ 未知错误：{e}")
        return None

def parse_sdn_data(csv_text):
    """解析 CSV 数据"""
    try:
        lines = csv_text.strip().split('\n')
        if len(lines) < 2:
            print("⚠️ 警告：CSV 数据为空或格式异常")
            return []
            
        headers = lines[0].split(',')
        print(f"📊 CSV 列名: {headers}")
        entities = []
        
        for i, line in enumerate(lines[1:], 1):
            values = line.split(',')
            if len(values) >= 3:
                entities.append({
                    'name': values[0].strip('"'),
                    'type': values[1].strip('"') if len(values) > 1 else '',
                    'programs': values[2].strip('"') if len(values) > 2 else ''
                })
        
        print(f"✅ 解析完成：共 {len(entities)} 个实体")
        return entities
    except Exception as e:
        print(f"❌ CSV 解析错误: {e}")
        traceback.print_exc()
        return []

def check_matches(entities, watchlist):
    """模糊匹配检查"""
    print(f"🔍 开始匹配检查，名单公司数: {len(watchlist['companies'])}")
    matches = []
    
    for entity in entities:
        for company in watchlist['companies']:
            candidates = [company['name']] + company.get('aliases', [])
            entity_name = entity['name']
            
            for candidate in candidates:
                # rapidfuzz 使用 0-100 的分数
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
                    break  # 该公司已匹配，跳过后续别名
    
    print(f"✅ 匹配完成：发现 {len(matches)} 个匹配项")
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
    print("=" * 50)
    print(f"🚀 SDN 监测任务开始 - {datetime.now()}")
    print("=" * 50)
    
    try:
        # 1. 加载配置
        print("\n📋 步骤 1: 加载配置...")
        config = load_config()
        print(f"   监测公司: {[c['name'] for c in config['companies']]}")
        
        # 2. 加载上次状态
        print("\n📝 步骤 2: 加载历史状态...")
        last_state = load_last_state()
        print(f"   上次检查: {last_state.get('last_check', '无')}")
        
        # 3. 获取 SDN 数据
        print("\n🌐 步骤 3: 获取 SDN 数据...")
        sdn_data = fetch_sdn_list()
        if not sdn_data:
            print("❌ 无法获取 SDN 数据，任务终止")
            sys.exit(1)
        
        # 4. 解析数据
        print("\n🔍 步骤 4: 解析数据...")
        entities = parse_sdn_data(sdn_data)
        if not entities:
            print("⚠️ 未解析到实体数据")
            sys.exit(1)
        
        # 5. 执行匹配
        print("\n🎯 步骤 5: 执行匹配...")
        current_matches = check_matches(entities, config)
        
        # 6. 检测新增
        print("\n🆕 步骤 6: 检测新增命中...")
        prev_matched_names = {m['matched_name'] for m in last_state.get('matched_entities', [])}
        new_matches = [m for m in current_matches if m['matched_name'] not in prev_matched_names]
        print(f"   新增命中: {len(new_matches)} 个")
        
        # 7. 判断是否推送
        should_alert = bool(new_matches) or config.get('alert_on_update', False)
        
        if should_alert:
            print("\n📤 步骤 7: 发送企业微信通知...")
            
            # 延迟导入，确保前面的步骤可以独立运行
            try:
                from wecom_bot import WeComBot
            except ImportError as e:
                print(f"❌ 导入 WeComBot 失败: {e}")
                sys.exit(1)
            
            bot_id = os.environ.get('WECOM_BOT_ID')
            secret = os.environ.get('WECOM_SECRET')
            recv_id = os.environ.get('WECOM_RECV_ID')
            
            if not all([bot_id, secret, recv_id]):
                print("❌ 环境变量缺失：请检查 WECOM_BOT_ID, WECOM_SECRET, WECOM_RECV_ID")
                sys.exit(1)
            
            print(f"   Bot ID: {bot_id[:10]}...")
            print(f"   Recv ID: {recv_id}")
            
            try:
                bot = WeComBot(bot_id=bot_id, secret=secret, recv_id=recv_id)
                message = format_alert_message(current_matches, is_update=config.get('alert_on_update'))
                
                if new_matches:
                    new_names = [m['matched_name'] for m in new_matches]
                    message += f"\n\n🆕 新增命中：{', '.join(new_names)}"
                
                result = bot.send_text_message(message)
                print(f"✅ 推送成功: {result}")
            except Exception as e:
                print(f"❌ 推送失败: {e}")
                traceback.print_exc()
                # 推送失败不退出，仍保存状态
        else:
            print("\n📤 步骤 7: 无需推送（无新增命中）")
        
        # 8. 保存状态
        print("\n💾 步骤 8: 保存状态...")
        save_state({
            "last_check": datetime.now().isoformat(),
           
