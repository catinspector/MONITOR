import json
import requests
import os
import sys
import traceback
from datetime import datetime
from rapidfuzz import fuzz


# 路径配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# 配置
OPEN_SANCTIONS_URL = "https://data.opensanctions.org/datasets/us_ofac_sdn/targets.simple.csv"
STATE_FILE = os.path.join(ROOT_DIR, "data", "last_check.json")
CONFIG_FILE = os.path.join(ROOT_DIR, "config", "watchlist.json")


def load_config():
    """加载监测配置"""
    print(f"   加载配置: {CONFIG_FILE}")
    
    if not os.path.exists(CONFIG_FILE):
        print(f"   ❌ 错误：找不到配置文件！")
        sys.exit(1)
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"   ✅ 配置加载成功，监测 {len(config.get('companies', []))} 家公司")
        return config
    except Exception as e:
        print(f"   ❌ 错误：{e}")
        sys.exit(1)


def load_last_state():
    """加载上次状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"   ⚠️ 读取状态失败: {e}")
    return {"last_check": None, "matched_entities": []}


def save_state(state):
    """保存状态"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"   💾 状态已保存")
    except Exception as e:
        print(f"   ⚠️ 保存状态失败: {e}")


def fetch_sdn_list():
    """获取 SDN 清单"""
    print("步骤 2: 获取 SDN 数据...")
    try:
        response = requests.get(OPEN_SANCTIONS_URL, timeout=30)
        response.raise_for_status()
        print(f"   ✅ 获取成功，数据大小: {len(response.text)} 字符")
        return response.text
    except Exception as e:
        print(f"   ❌ 获取失败: {e}")
        return None


def parse_sdn_data(csv_text):
    """解析 CSV"""
    lines = csv_text.strip().split('\n')
    entities = []
    
    for line in lines[1:]:  # 跳过表头
        values = line.split(',')
        if len(values) >= 3:
            entities.append({
                'name': values[0].strip('"'),
                'type': values[1].strip('"'),
                'programs': values[2].strip('"')
            })
    
    print(f"   📊 解析完成：共 {len(entities)} 个实体")
    return entities


def check_matches(entities, watchlist):
    """模糊匹配"""
    print("步骤 3: 匹配检查...")
    matches = []
    
    for entity in entities:
        for company in watchlist['companies']:
            aliases = company.get('aliases', [])
            if isinstance(aliases, str):
                aliases = [aliases]
            
            candidates = [company['name']] + aliases
            
            for candidate in candidates:
                score = fuzz.token_set_ratio(candidate, entity['name'])
                threshold = company.get('confidence_threshold', 0.75) * 100
                
                if score >= threshold and score >= watchlist.get('min_match_score', 70):
                    matches.append({
                        'watch_name': company['name'],
                        'matched_name': entity['name'],
                        'type': entity['type'],
                        'programs': entity['programs'],
                        'score': round(score, 1)
                    })
                    print(f"   ✓ 命中: {entity['name']} (得分: {score}%)")
                    break
    
    print(f"   🎯 总计发现 {len(matches)} 个匹配")
    return matches


def format_markdown_message(all_matches, new_matches, check_time):
    """格式化消息 - 显示所有命中，并标注新增"""
    lines = []
    lines.append("## 🚨 SDN 制裁清单监测报告")
    lines.append("")
    
    # 统计信息
    lines.append(f"**📊 监测结果：发现 {len(all_matches)} 个命中**")
    if new_matches:
        lines.append(f"**🔴 其中新增 {len(new_matches)} 个**")
    lines.append("")
    
    # 显示所有命中
    for idx, match in enumerate(all_matches, 1):
        # 标记新增的
        is_new = any(m['matched_name'] == match['matched_name'] for m in new_matches)
        new_flag = "🔴 " if is_new else ""
        
        lines.append(f"{idx}. {new_flag}**{match['watch_name']}** → `{match['matched_name']}`")
        lines.append(f"   - 类型：{match['type']}")
        lines.append(f"   - 制裁项目：{match['programs']}")
        lines.append(f"   - 匹配度：{match['score']}%")
        lines.append("")
    
    lines.append("---")
    lines.append(f"⏰ 检查时间：{check_time}")
    lines.append("📡 数据来源：US OFAC SDN List (OpenSanctions)")
    
    return "\n".join(lines)


def main():
    print(f"🚀 SDN 监测任务开始 - {datetime.now()}")
    print("=" * 60)
    
    try:
        # 1. 加载配置
        print("步骤 1: 加载配置...")
        config = load_config()
        
        # 2. 获取数据
        sdn_data = fetch_sdn_list()
        if not sdn_data:
            sys.exit(1)
        
        entities = parse_sdn_data(sdn_data)
        
        # 3. 匹配
        current_matches = check_matches(entities, config)
        
        # 4. 检测新增（用于标记，不影响推送）
        print("步骤 4: 检测历史记录...")
        last_state = load_last_state()
        prev_matched_names = {m['matched_name'] for m in last_state.get('matched_entities', [])}
        new_matches = [m for m in current_matches if m['matched_name'] not in prev_matched_names]
        
        if new_matches:
            print(f"   🆕 新增命中：{len(new_matches)} 个")
        else:
            print(f"   无新增命中")
        
        # 5. 关键修改：只要有命中就推送（不管是否新增）
        if current_matches:
            print(f"步骤 5: 发送企业微信通知（发现 {len(current_matches)} 个命中）...")
            
            webhook_key = os.environ.get('WECOM_WEBHOOK_KEY')
            if not webhook_key:
                print("   ❌ 错误：未设置 WECOM_WEBHOOK_KEY")
                print("   请配置 GitHub Secret: WECOM_WEBHOOK_KEY")
                sys.exit(1)
            
            try:
                from wecom_bot import send_wecom_message
                
                check_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                message = format_markdown_message(current_matches, new_matches, check_time)
                
                send_wecom_message(message)
                print("   ✅ 推送成功")
                
            except Exception as e:
                print(f"   ❌ 推送失败: {e}")
                traceback.print_exc()
        else:
            print("步骤 5: 未命中任何监测对象，跳过推送")
        
        # 6. 保存状态
        print("步骤 6: 保存状态...")
        save_state({
            "last_check": datetime.now().isoformat(),
            "entity_count": len(entities),
            "matched_entities": current_matches
        })
        
        print("=" * 60)
        print("✅ 监测任务完成")
        
    except Exception as e:
        print(f"❌ 任务失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
