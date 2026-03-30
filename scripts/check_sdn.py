import json
import requests
import os
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from rapidfuzz import fuzz

# --- 路径配置 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# 【修改】重新指向 JSON 配置文件
CONFIG_FILE = os.path.join(ROOT_DIR, "config", "watchlist.json") 
STATE_FILE = os.path.join(ROOT_DIR, "data", "last_check.json")
OPEN_SANCTIONS_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"

def load_config():
    """【修改】从 JSON 加载监测配置"""
    print(f"   加载 JSON 配置: {CONFIG_FILE}")
    if not os.path.exists(CONFIG_FILE):
        print(f"   ❌ 错误：找不到 JSON 配置文件！")
        sys.exit(1)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"   ❌ 错误：读取 JSON 失败 - {e}")
        sys.exit(1)

def load_last_state():
    """【修复】加载上次状态"""
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
    """获取 SDN 数据"""
    print("步骤 2: 获取 SDN 数据...")
    try:
        response = requests.get(OPEN_SANCTIONS_URL, timeout=60)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"   ❌ 获取失败: {e}")
        return None

def parse_sdn_data(xml_text):
    """解析 XML"""
    print("   解析 OFAC XML...")
    try:
        root = ET.fromstring(xml_text)
        ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
        entries = root.findall('ns:sdnEntry', ns) if ns else root.findall('sdnEntry')
        
        entities = []
        for entry in entries:
            fn = entry.find('ns:firstName', ns).text if entry.find('ns:firstName', ns) is not None else ""
            ln = entry.find('ns:lastName', ns).text if entry.find('ns:lastName', ns) is not None else ""
            full_name = f"{fn} {ln}".strip() if fn else ln.strip()
            
            if not full_name: continue
            
            aka_names = []
            aka_list = entry.find('ns:akaList', ns)
            if aka_list is not None:
                for aka in aka_list.findall('ns:aka', ns):
                    afn = aka.find('ns:firstName', ns).text if aka.find('ns:firstName', ns) is not None else ""
                    aln = aka.find('ns:lastName', ns).text if aka.find('ns:lastName', ns) is not None else ""
                    aka_names.append(f"{afn} {aln}".strip() if afn else aln.strip())

            entities.append({
                'name': full_name,
                'aliases': aka_names,
                'type': entry.find('ns:sdnType', ns).text if entry.find('ns:sdnType', ns) is not None else "Unknown",
                'programs': "; ".join([p.text for p in entry.findall('.//ns:program', ns) if p.text])
            })
        return entities
    except Exception as e:
        print(f"   ❌ XML 解析错误: {e}")
        return []

def check_matches(entities, watchlist):
    """【保持新逻辑】判定逻辑：所有 name 或 alias 命中任意一个就算成功"""
    print("步骤 3: 匹配检查...")
    matches = []
    seen_sdn = set()
    
    for company in watchlist.get('companies', []):
        # 汇总监测词：JSON 里的 name 和 aliases 列表
        search_terms = [company['name'].lower()]
        if company.get('aliases'):
            search_terms.extend([a.lower() for a in company['aliases']])
        
        for entity in entities:
            if entity['name'] in seen_sdn: continue
            
            # 汇总 SDN 词：官方名和官方别名
            sdn_ids = [entity['name'].lower()] + [aka.lower() for aka in entity.get('aliases', [])]
            
            is_hit = False
            hit_score = 0
            
            # 遍历每一个搜索词去撞 SDN 的每一个名称
            for term in search_terms:
                if not term: continue
                for sdn_id in sdn_ids:
                    # 1. 包含匹配
                    if term in sdn_id:
                        is_hit = True
                        hit_score = 100.0
                        break
                    # 2. 高分模糊匹配 (针对较长词)
                    if len(term) > 5:
                        score = fuzz.token_set_ratio(term, sdn_id)
                        if score >= 95:
                            is_hit = True
                            hit_score = score
                            break
                if is_hit: break
            
            if is_hit:
                matches.append({
                    'watch_name': company['name'],
                    'matched_name': entity['name'],
                    'type': entity['type'],
                    'programs': entity['programs'],
                    'score': round(hit_score, 1)
                })
                seen_sdn.add(entity['name'])
    return matches

def format_markdown_message(all_matches, new_matches, check_time):
    """
    格式化企业微信 Markdown 消息 
    """
    # 标题与统计
    lines = [
        "### 🚨 SDN 制裁清单监测报告",
        f"> 📊 监测结果：发现 **{len(all_matches)}** 个命中",
        f"> 🔴 其中新增：**{len(new_matches)}** 个",
        ""
    ]
    
    # 记录所有新增命中的名称，用于比对
    new_names = {m['matched_name'] for m in new_matches}
    
    for idx, match in enumerate(all_matches, 1):
        # 判定是否为新增，显示对应的图标
        is_new = match['matched_name'] in new_names
        status_icon = "🔴" if is_new else "⚪"
        
        # 第一行：序号、状态标识、监控名 -> 命中名
        lines.append(f"{idx}. {status_icon} **{match['watch_name']}**")
        lines.append(f"　 ➔ <font color=\"warning\">{match['matched_name']}</font>")
        
        # 详细信息列表（使用全角空格对齐）
        if match.get('matched_aliases'):
            aliases_str = ", ".join(match['matched_aliases'])
            lines.append(f"　 - **别名**：{aliases_str}")
            
        lines.append(f"　 - **类型**：{match['type']}")
        lines.append(f"　 - **项目**：{match['programs']}")
        lines.append(f"　 - **匹配度**：`{match['score']}%`")
        lines.append("") # 条目间空行

    # 页脚
    lines.append("---")
    lines.append(f"<font color=\"comment\">⏰ 检查时间：{check_time}</font>")
    lines.append("<font color=\"comment\">📡 数据来源：US OFAC SDN List</font>")
    
    return "\n".join(lines)

def main():
    print(f"🚀 SDN 监测任务开始 - {datetime.now()}")
    try:
        config = load_config()
        sdn_data = fetch_sdn_list()
        if not sdn_data: sys.exit(1)
        
        entities = parse_sdn_data(sdn_data)
        current_matches = check_matches(entities, config)
        
        last_state = load_last_state()
        prev_names = {m['matched_name'] for m in last_state.get('matched_entities', [])}
        new_matches = [m for m in current_matches if m['matched_name'] not in prev_names]
        
        if current_matches:
            webhook_key = os.environ.get('WECOM_WEBHOOK_KEY')
            if webhook_key:
                from wecom_bot import send_wecom_message
                msg = format_markdown_message(current_matches, new_matches, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                send_wecom_message(msg)
        
        save_state({"last_check": datetime.now().isoformat(), "matched_entities": current_matches})
        print("✅ 监测任务完成")
    except Exception:
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
