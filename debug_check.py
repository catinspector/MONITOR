import requests
from rapidfuzz import fuzz

url = "https://data.opensanctions.org/datasets/us_ofac_sdn/targets.simple.csv"
print("正在下载 SDN 数据...")
response = requests.get(url)
lines = response.text.split('\n')

# 你的监测关键词
keywords = ["Kovrov", "Atomenergoprom", "Rosatom", "Atomic Energy", "Ковровский", "Атомэнергопром"]

print("\n=== 搜索相关实体 ===")
matches = []
for line in lines[1:]:
    values = line.split(',')
    if len(values) >= 3:
        name = values[0].strip('"')
        for keyword in keywords:
            if keyword.lower() in name.lower():
                matches.append((name, values[1].strip('"'), values[2].strip('"')))
                print(f"找到: {name} | 类型: {values[1]} | 项目: {values[2]}")
                break

if not matches:
    print("未找到匹配，显示前 100 个实体供参考：")
    for i, line in enumerate(lines[1:101]):
        values = line.split(',')
        if values:
            print(f"{i+1}. {values[0].strip('"')}")

# 测试你的配置名称是否能匹配
print("\n=== 匹配测试 ===")
test_names = [
    "Kovrov Mechanical Plant",
    "Kovrovsky Mekhanichesky Zavod", 
    "Atomenergoprom",
    "Atomic Energy Power Corporation"
]

for test in test_names:
    print(f"\n测试: {test}")
    best_score = 0
    best_match = ""
    for line in lines[1:]:
        values = line.split(',')
        if values:
            sdn_name = values[0].strip('"')
            score = fuzz.token_set_ratio(test, sdn_name)
            if score > best_score:
                best_score = score
                best_match = sdn_name
    print(f"  最佳匹配: {best_match} (得分: {best_score}%)")
