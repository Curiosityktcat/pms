#!/usr/bin/env python3
"""本机 Qwen3.6 vs 在线 DeepSeek 效果对比小工具。

用同一段 system+user 提示词分别打到两个模型，并排打印输出、耗时、token 用量，
便于人工判断「本地 Qwen3.6 能否替代 DeepSeek」。本地够好就切回本地省钱。

用法：
    cd /home/huangxb/pms/backend
    python3 tools/compare_models.py                 # 用内置示例提示词
    python3 tools/compare_models.py prompt.txt       # 用文件内容作为 user 提示词

可选环境变量：
    QWEN_API   本地 Qwen 端点（默认 http://127.0.0.1:8080/v1/chat/completions）
    QWEN_NAME  本地模型名（llama.cpp 忽略具体值，默认 qwen3.6）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from services.llm_client import chat, get_llm_config

QWEN_CFG = {
    "api": os.environ.get("QWEN_API", "http://127.0.0.1:8080/v1/chat/completions"),
    "name": os.environ.get("QWEN_NAME", "qwen3.6"),
    "key": "local",
}

DEFAULT_SYSTEM = "你是医院政府采购评审专家助手，回答需严谨、可追溯。"
DEFAULT_USER = (
    "下面是一条采购资格审查条目，请判断它是否要求投标人提供佐证材料，"
    "并说明承诺制下应如何判定：\n"
    "「具有良好的财务状况：提供经审计的近一年财务报告或基本开户行出具的资信证明复印件。」"
)


def run_one(label, cfg, system, user):
    t0 = time.time()
    try:
        text = chat(system, user, cfg=cfg, temperature=0.1,
                    max_tokens=1024, timeout=300)
        dt = time.time() - t0
        return {"label": label, "ok": True, "text": text, "secs": dt}
    except Exception as e:
        return {"label": label, "ok": False, "text": f"调用失败：{e}",
                "secs": time.time() - t0}


def main():
    user = DEFAULT_USER
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            user = f.read()

    app = create_app()
    with app.app_context():
        deepseek_cfg = get_llm_config()  # 当前 SysConfig：DeepSeek
        targets = [("DeepSeek（在线·当前）", deepseek_cfg),
                   ("Qwen3.6（本机·免费）", QWEN_CFG)]
        results = [run_one(lbl, cfg, DEFAULT_SYSTEM, user) for lbl, cfg in targets]

    print("\n" + "=" * 72)
    print("【提示词】", user[:120].replace("\n", " "), "...\n")
    for r in results:
        print("─" * 72)
        print(f"■ {r['label']}    用时 {r['secs']:.1f}s    {'OK' if r['ok'] else '失败'}")
        print("─" * 72)
        print(r["text"].strip())
        print()
    print("=" * 72)
    print("提示：本地 Qwen3.6 输出质量若接近 DeepSeek，可在后台「大模型设置」把端点切到")
    print("      http://127.0.0.1:8080/v1/chat/completions 省下 DeepSeek 的费用。")


if __name__ == "__main__":
    main()
