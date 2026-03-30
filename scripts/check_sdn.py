import json
import requests
import os
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from rapidfuzz import fuzz
import pandas as pd  # 新增导入 [cite: 1, 2]


# 路径配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# OFAC 官方 SDN XML
OPEN_SANCTIONS_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"
STATE_FILE = os.path.join(ROOT_DIR, "data", "last_check.json")
CONFIG_FILE = os.path.join(ROOT_DIR, "config", "watchlist.json")


# 路径配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# 修改：配置文件后缀改为 .xlsx
CONFIG_FILE = os.path.join(ROOT_DIR, "config", "watchlist.xlsx") 

def load_config():
    """从 Excel 加载监测配置"""
    print(f"   加载 Excel 配置: {CONFIG_FILE}")
    
    if not os.path.exists(CONFIG_FILE):
        print(f"   ❌ 错误：找不到 Excel 配置文件！")
        sys.exit(1)
    
    try:
        # 使用 pandas 读取 Excel 文件 [cite: 1, 2]
        df = pd.read_excel(CONFIG_FILE)
        
        # 转换数据格式以适配原有的匹配逻辑
        companies = []
        for _, row in df.iterrows():
            name = str(row.get('name', '')).strip()
            if not name or name == 'nan': continue
            
            # 处理别名：支持用分号或逗号分隔
            raw_aliases = str(row.get('aliases', '')).replace('；', ';').replace('，', ',')
            if raw_aliases and raw_aliases != 'nan':
                alias_list = [a.strip() for a in raw_aliases.split(';') if a.strip()]
            else:
                alias_list = []
                
            companies.append({
                'name': name,
                'aliases': alias_list
            })
            
        print(f"   ✅ 成功加载 {len(companies)} 条监测对象")
        return {'companies': companies}
    except Exception as e:
        print(f"   ❌ 错误：读取 Excel 失败 - {e}")
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
    """获取 OFAC SDN XML"""
    print("步骤 2: 获取 SDN 数据...")
    try:
        response = requests.get(OPEN_SANCTIONS_URL, timeout=60)
        response.raise_for_status()
        print(f"   ✅ 获取成功，数据大小: {len(response.text)} 字符")
        return response.text
    except Exception as e:
        print(f"   ❌ 获取失败: {e}")
        return None

def parse_sdn_data(xml_text):
    """解析 OFAC 官方 SDN XML"""
    print("   解析 OFAC XML...")
    
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"   ❌ XML 解析错误: {e}")
        return []
    
    # 提取命名空间
    ns = {}
    if '}' in root.tag:
        ns_url = root.tag.split('}')[0].strip('{')
        ns = {'ns': ns_url}
    
    print(f"   📅 发布日期: {root.find('ns:publshInformation/ns:Publish_Date', ns).text if root.find('ns:publshInformation/ns:Publish_Date', ns) is not None else 'Unknown'}")
    print(f"   📊 记录数: {root.find('ns:publshInformation/ns:Record_Count', ns).text if root.find('ns:publshInformation/ns:Record_Count', ns) is not None else 'Unknown'}")
    
    # 使用命名空间查找所有 sdnEntry
    entries = root.findall('ns:sdnEntry', ns)
    print(f"   找到 {len(entries)} 个实体")
    
    entities = []
    
    for entry in entries:
        try:
            # 使用命名空间获取字段
            first_name = entry.find('ns:firstName', ns)
            last_name = entry.find('ns:lastName', ns)
            
            name = ''
            if last_name is not None and last_name.text:
                name = last_name.text.strip()
            if first_name is not None and first_name.text:
                if name:
                    name = f"{first_name.text.strip()} {name}"
                else:
                    name = first_name.text.strip()
            
            if not name:
                continue
            
            # 类型
            sdn_type = entry.find('ns:sdnType', ns)
            entity_type = sdn_type.text.strip() if sdn_type is not None else 'Unknown'
            
            # 制裁项目
            programs = []
            program_list = entry.find('ns:programList', ns)
            if program_list is not None:
                for prog in program_list.findall('ns:program', ns):
                    if prog.text:
                        programs.append(prog.text.strip())
            
            # 别名
            aliases = []
            aka_list = entry.find('ns:akaList', ns)
            if aka_list is not None:
                for aka in aka_list.findall('ns:aka', ns):
                    aka_first = aka.find('ns:firstName', ns)
                    aka_last = aka.find('ns:lastName', ns)
                    
                    aka_name = ''
                    if aka_last is not None and aka_last.text:
                        aka_name = aka_last.text.strip()
                    if aka_first is not None and aka_first.text:
                        if aka_name:
                            aka_name = f"{aka_first.text.strip()} {aka_name}"
                        else:
                            aka_name = aka_first.text.strip()
                    
                    if aka_name and aka_name != name:
                        aliases.append(aka_name)
            
            entities.append({
                'name': name,
                'aliases': aliases,
                'type': entity_type,
                'programs': '; '.join(programs) if programs else 'SDN'
            })
            
        except Exception:
            continue
    
    print(f"   ✅ 解析完成：共 {len(entities)} 个实体")
    
    # 验证 Kovrov
    kovrov_list = [e for e in entities if 'kovrov' in e['name'].lower()]
    print(f"   🔍 验证: 找到 {len(kovrov_list)} 个 Kovrov")
    if kovrov_list:
        print(f"      例如: {kovrov_list[0]['name']}")
        print(f"      别名: {kovrov_list[0]['aliases'][:3]}")
    
    return entities


def check_matches(entities, watchlist):
    """严格匹配 - 必须包含独特关键词"""
    print("步骤 3: 匹配检查...")
    matches = []
    seen = set()
    
    for company in watchlist['companies']:
        # 提取独特关键词（长度>4且非通用词）
        unique_terms = [company['name'].lower()]
        aliases = company.get('aliases', [])
        if isinstance(aliases, str):
            aliases = [aliases]
        unique_terms.extend([a.lower() for a in aliases])
        
        print(f"   监测: {company['name']}")
        
        for entity in entities:
            if entity['name'] in seen:
                continue
            
            csv_identifiers = [entity['name']] + entity.get('aliases', [])
            
            # 策略1：完整子串匹配（最准确）
            full_match = False
            for term in unique_terms:
                for csv_id in csv_identifiers:
                    # 清理后的完整匹配
                    if term in csv_id.lower():
                        full_match = True
                        score = 100.0
                        break
                if full_match:
                    break
            
            # 策略2：高模糊匹配（>=95%）且包含主要词
            high_score_match = False
            if not full_match:
                for term in unique_terms:
                    for csv_id in csv_identifiers:
                        score = fuzz.token_set_ratio(term, csv_id)
                        # 要求：高得分 AND 包含独特词（如kovrov/atomenergo）
                        if score >= 95:
                            # 检查是否包含独特词（至少1个长度>5的词）
                            term_words = [w for w in term.split() if len(w) > 5]
                            csv_text = csv_id.lower()
                            has_unique_word = any(w in csv_text for w in term_words)
                            if has_unique_word:
                                high_score_match = True
                                break
                    if high_score_match:
                        break
            
            if full_match or high_score_match:
                matches.append({
                    'watch_name': company['name'],
                    'matched_name': entity['name'],
                    'matched_aliases': entity.get('aliases', [])[:2],
                    'type': entity['type'],
                    'programs': entity['programs'],
                    'score': round(score if 'score' in dir() else 100.0, 1)
                })
                seen.add(entity['name'])
                match_type = "完整匹配" if full_match else "高得分匹配"
                print(f"      ✓ 命中: {entity['name']} ({match_type})")
    
    print(f"   🎯 总计发现 {len(matches)} 个匹配")
    return matches
    

def format_markdown_message(all_matches, new_matches, check_time):
    """格式化消息"""
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
        if match.get('matched_aliases'):
            lines.append(f"   - 别名：{', '.join(match['matched_aliases'])}")
        lines.append(f"   - 类型：{match['type']}")
        lines.append(f"   - 制裁项目：{match['programs']}")
        lines.append(f"   - 匹配度：{match['score']}%")
        lines.append("")
    
    lines.append("---")
    lines.append(f"⏰ 检查时间：{check_time}")
    lines.append("📡 数据来源：US OFAC SDN List (Official)")
    
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
        
        # 3. 解析 XML
        entities = parse_sdn_data(sdn_data)
        if not entities:
            print("❌ 未解析到实体")
            sys.exit(1)
        
        # 4. 匹配
        current_matches = check_matches(entities, config)
        
        # 5. 检测新增
        print("步骤 4: 检测历史记录...")
        last_state = load_last_state()
        prev_names = {m['matched_name'] for m in last_state.get('matched_entities', [])}
        new_matches = [m for m in current_matches if m['matched_name'] not in prev_names]
        
        if new_matches:
            print(f"   🆕 新增命中：{len(new_matches)} 个")
        else:
            print(f"   无新增命中")
        
        # 6. 推送（只要有命中就推送）
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
        
        # 7. 保存状态
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
