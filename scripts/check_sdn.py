import csv
import io
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
            return json.load(f)
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
    """解析 CSV - 带原始调试"""
    print("   解析 CSV...")
    
    # 先打印前 5 行原始内容看格式
    print("   [调试] 原始 CSV 前5行:")
    lines = csv_text.split('\n')
    for i, line in enumerate(lines[:6]):
        print(f"      行{i}: {line[:150]}")
    
    entities = []
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    print(f"   [调试] 表头: {header}")
    print(f"   [调试] 表头列数: {len(header)}")
    
    for i, row in enumerate(reader):
        if i < 3:  # 只打印前3行数据看结构
            print(f"   [调试] 数据行{i}: {row}")
            print(f"      列数: {len(row)}")
            if len(row) >= 3:
                print(f"      第1列: '{row[0]}'")
                print(f"      第2列: '{row[1]}'")
                print(f"      第3列: '{row[2]}'")
            if len(row) >= 4:
                print(f"      第4列: '{row[3]}'")
        
        if len(row) >= 4:
            entities.append({
                'id': row[0].strip(),
                'type': row[1].strip(),
                'name': row[2].strip(),
                'alias': row[3].strip()
            })
        elif len(row) >= 3:
            entities.append({
                'id': row[0].strip(),
                'type': row[1].strip(),
                'name': row[2].strip(),
                'alias': ''
            })
    
    print(f"   📊 解析完成：共 {len(entities)} 个实体")
    
    # 再次搜索 Kovrov（不区分大小写）
    kovrov_list = [e for e in entities if 'kovrov' in e.get('name', '').lower()]
    print(f"   🔍 验证: 找到 {len(kovrov_list)} 个 Kovrov")
    
    # 如果没有找到，打印包含 'Mechanical' 的看是否有数据
    if not kovrov_list:
        mech_list = [e for e in entities if 'mechanical' in e.get('name', '').lower()]
        print(f"   🔍 备用验证: 找到 {len(mech_list)} 个 Mechanical")
        if mech_list:
            print(f"      例如: {mech_list[0]}")
    
    return entities


def check_matches(entities, watchlist):
    """极端调试版本 - 打印所有比较过程"""
    print("步骤 3: 匹配检查（调试模式）...")
    matches = []
    seen = set()
    
    # 先打印配置内容确认
    print(f"   [调试] 配置公司数: {len(watchlist['companies'])}")
    for company in watchlist['companies']:
        print(f"   [调试] 监测对象: {company['name']}, aliases: {company.get('aliases', [])}")
    
    # 找前5个包含 Kovrov 的实体用于调试
    kovrov_entities = [e for e in entities if 'kovrov' in e['name'].lower()]
    print(f"   [调试] CSV 中找到 {len(kovrov_entities)} 个 Kovrov 实体")
    if kovrov_entities:
        test_entity = kovrov_entities[0]
        print(f"   [调试] 测试实体 name: '{test_entity['name']}'")
        print(f"   [调试] 测试实体 alias: '{test_entity['alias']}'")
        print(f"   [调试] 测试实体 name 长度: {len(test_entity['name'])}")
        print(f"   [调试] 测试实体 name ASCII: {[ord(c) for c in test_entity['name']]}")
    
    for entity in entities:
        if 'kovrov' not in entity['name'].lower():
            continue  # 只调试 Kovrov 相关
        
        print(f"\n   [详细调试] 检查实体: '{entity['name']}'")
        
        csv_ids = [entity['name']]
        if entity.get('alias'):
            csv_ids.append(entity['alias'])
        
        for company in watchlist['companies']:
            config_ids = [company['name']]
            aliases = company.get('aliases', [])
            if isinstance(aliases, str):
                aliases = [aliases]
            config_ids.extend(aliases)
            
            print(f"      对比公司: {company['name']}")
            
            for config_id in config_ids:
                for csv_id in csv_ids:
                    # 计算各种匹配方式
                    score = fuzz.token_set_ratio(config_id, csv_id)
                    config_lower = config_id.lower().strip()
                    csv_lower = csv_id.lower().strip()
                    
                    # 多种包含检查
                    contained = config_lower in csv_lower or csv_lower in config_lower
                    exact_match = config_lower == csv_lower
                    
                    print(f"         对比: '{config_id}' vs '{csv_id}'")
                    print(f"            模糊得分: {score}, 子串匹配: {contained}, 完全匹配: {exact_match}")
                    
                    # 临时降低阈值到 50 测试
                    threshold = company.get('confidence_threshold', 0.75) * 100
                    if score >= threshold or contained:
                        print(f"            >>> 应该命中! <<<")
                        if entity['name'] not in seen:
                            matches.append({
                                'watch_name': company['name'],
                                'matched_name': entity['name'],
                                'matched_alias': entity.get('alias', ''),
                                'type': entity['type'],
                                'programs': entity['programs'],
                                'score': round(score, 1)
                            })
                            seen.add(entity['name'])
                            print(f"            >>> 已添加到匹配列表 <<<")
                        break
                if entity['name'] in seen:
                    break
            if entity['name'] in seen:
                break
    
    print(f"\n   🎯 调试结束，总计匹配: {len(matches)} 个")
    return matches


def format_markdown_message(all_matches, new_matches, check_time):
    """格式化 Markdown 消息"""
    lines = []
    lines.append("## 🚨 SDN 制裁清单监测报告")
    lines.append("")
    
    lines.append(f"**📊 监测结果：发现 {len(all_matches)} 个命中**")
    if new_matches:
        lines.append(f"**🔴 其中新增 {len(new_matches)} 个**")
    lines.append("")
    
    for idx, match in enumerate(all_matches, 1):
        is_new = any(m['matched_name'] == match['matched_name'] for m in new_matches)
        new_flag = "🔴 " if is_new else ""
        
        lines.append(f"{idx}. {new_flag}**{match['watch_name']}** → `{match['matched_name']}`")
        if match.get('matched_alias'):
            lines.append(f"   - 别名：{match['matched_alias']}")
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
        if not entities:
            print("错误：未解析到实体")
            sys.exit(1)
        
        # 3. 匹配检查
        current_matches = check_matches(entities, config)
        
        # 4. 检测新增（仅用于标记，不控制推送）
        print("步骤 4: 检测历史记录...")
        last_state = load_last_state()
        prev_names = {m['matched_name'] for m in last_state.get('matched_entities', [])}
        new_matches = [m for m in current_matches if m['matched_name'] not in prev_names]
        
        if new_matches:
            print(f"   🆕 新增命中：{len(new_matches)} 个")
        else:
            print(f"   无新增命中")
        
        # 5. 关键：只要有命中就推送（不管是否新增）
        if current_matches:
            print(f"步骤 5: 发送企业微信通知（发现 {len(current_matches)} 个命中）...")
            
            webhook_key = os.environ.get('WECOM_WEBHOOK_KEY')
            if not webhook_key:
                print("   ❌ 错误：未设置 WECOM_WEBHOOK_KEY")
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
