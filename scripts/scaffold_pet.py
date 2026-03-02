#!/usr/bin/env python3
"""
Peko 快速新增宠物脚手架（仿 SimuEngine 的 scaffold_topic）
用法：在项目根目录执行
  python scripts/scaffold_pet.py <宠物id> "<宠物名称>" "[作者]"
示例：
  python scripts/scaffold_pet.py hamster "仓鼠"
  python scripts/scaffold_pet.py dog "小狗" "我"
会在 pets/<宠物id>/ 下生成 pet_config.json 和 resource 目录；
将动画帧放入 pets/<id>/resource/ 下对应状态目录即可，每个宠物独立 resource，无公共模块。
"""
import os
import sys
import json
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PETS_DIR = os.path.join(ROOT, "pets")
RESOURCE_DIR = "resource"  # 每个宠物独立 resource，与 pet_manager 一致


def main():
    if len(sys.argv) < 3:
        print("用法: python scripts/scaffold_pet.py <宠物id> \"<宠物名称>\" \"[作者]\"")
        print('示例: python scripts/scaffold_pet.py hamster "仓鼠"')
        sys.exit(1)

    pet_id = sys.argv[1].strip().lower().replace(" ", "-")
    pet_name = sys.argv[2].strip()
    author = sys.argv[3].strip() if len(sys.argv) > 3 else "Peko"

    if not re.match(r"^[a-z0-9][a-z0-9\-]*$", pet_id):
        print("宠物 id 请使用小写字母、数字和连字符，例如: hamster, my-dog")
        sys.exit(1)

    target_dir = os.path.join(PETS_DIR, pet_id)
    if os.path.isdir(target_dir) and os.path.isfile(os.path.join(target_dir, "pet_config.json")):
        print(f"已存在宠物目录且含配置: {target_dir}")
        sys.exit(1)

    os.makedirs(target_dir, exist_ok=True)
    resource_dir = os.path.join(target_dir, RESOURCE_DIR)
    os.makedirs(resource_dir, exist_ok=True)
    for state in ("stand", "walk_left", "walk_right", "walk_up", "walk_down"):
        os.makedirs(os.path.join(resource_dir, state), exist_ok=True)

    config = {
        "id": pet_id,
        "name": pet_name,
        "description": f"我是{pet_name}，用 L+Enter 和我对话吧",
        "version": "1.0.0",
        "author": author,
        "character": {
            "name": pet_name,
            "systemPrompt": f"你现在正在扮演一个可爱的桌面宠物，名字叫做{pet_name}。请用简短、可爱的语气和用户对话。"
        },
        "animations": {
            "stand": [f"{RESOURCE_DIR}/stand/0.png", f"{RESOURCE_DIR}/stand/1.png"],
            "walk_left": [f"{RESOURCE_DIR}/walk_left/0.png", f"{RESOURCE_DIR}/walk_left/1.png"],
            "walk_right": [f"{RESOURCE_DIR}/walk_right/0.png", f"{RESOURCE_DIR}/walk_right/1.png"],
            "walk_up": [f"{RESOURCE_DIR}/walk_up/0.png", f"{RESOURCE_DIR}/walk_up/1.png"],
            "walk_down": [f"{RESOURCE_DIR}/walk_down/0.png", f"{RESOURCE_DIR}/walk_down/1.png"],
            "dragged": [f"{RESOURCE_DIR}/stand/0.png", f"{RESOURCE_DIR}/stand/1.png"]
        },
        "actionConfig": {
            "stateSwitchInterval": 3000,
            "frameRate": 2,
            "moveSpeed": 5
        },
        "bubbleStyle": {},
        "slots": {}
    }

    config_path = os.path.join(target_dir, "pet_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"已创建宠物: {pet_name} ({pet_id})")
    print(f"  目录: {target_dir}")
    print(f"  配置: {config_path}")
    print("")
    print("下一步:")
    print("  1. 将动画帧放入 pets/" + pet_id + "/" + RESOURCE_DIR + "/ 下对应状态目录（stand, walk_left 等）")
    print("  2. 可选：放入 " + RESOURCE_DIR + "/icon.png 作为托盘图标（缺省时使用 stand 首帧）")
    print("  3. 在 pet_config.json 中按需修改 character.systemPrompt、bubbleStyle、slots")
    print("  4. 运行 python main.py，在托盘「切换宠物」中选择 " + pet_name)


if __name__ == "__main__":
    main()
