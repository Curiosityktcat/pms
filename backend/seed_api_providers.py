"""一次性种子：把机器上已有的各家 LLM API 登记进「API 管理」台账。

key 来源：DeepSeek=sys_config 现值；agnesai=~/ccgp/.env；Gemini=~/cga/.env。
表非空时跳过（幂等），可重复执行。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db
from models.api_provider import ApiProvider
from models.sys_config import SysConfig


def _env_val(path, key):
    try:
        for line in open(os.path.expanduser(path), encoding="utf-8"):
            m = re.match(rf"\s*{key}\s*=\s*[\"']?([^\"'\s]+)", line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return ""


def main():
    app = create_app()
    with app.app_context():
        if ApiProvider.query.count():
            print("api_providers 已有数据，跳过种子")
            return

        row = db.session.get(SysConfig, "scraper_api_key")
        deepseek_key = row.value if row else ""
        agnes1 = _env_val("~/ccgp/.env", "AGNES_API_KEY")
        agnes2 = _env_val("~/ccgp/.env", "AGNES_API_KEY2")
        gemini = _env_val("~/cga/.env", "GEMINI_API_KEY")

        rows = [
            ApiProvider(name="DeepSeek", kind="chat", sort=1,
                        base_url="https://api.deepseek.com/v1/chat/completions",
                        model_name="deepseek-v4-flash", api_key=deepseek_key,
                        transport="requests",
                        note="按量计费成本较高；当前全局对话模型"),
            ApiProvider(name="agnesai 账号1", kind="chat", sort=2,
                        base_url="https://apihub.agnes-ai.com/v1/chat/completions",
                        model_name="agnes-2.0-flash", api_key=agnes1,
                        transport="curl",
                        note="与账号2轮换分摊限额；本机代理下必须走 curl 通道"),
            ApiProvider(name="agnesai 账号2", kind="chat", sort=3,
                        base_url="https://apihub.agnes-ai.com/v1/chat/completions",
                        model_name="agnes-2.0-flash", api_key=agnes2,
                        transport="curl",
                        note="与账号1轮换分摊限额；本机代理下必须走 curl 通道"),
            ApiProvider(name="Gemini", kind="chat", sort=4,
                        base_url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                        model_name="gemini-2.5-flash", api_key=gemini,
                        transport="curl",
                        note="OpenAI 兼容端点；本机代理下必须走 curl 通道"),
            ApiProvider(name="本地 Qwen（llama.cpp）", kind="chat", sort=5,
                        base_url="http://127.0.0.1:8080/v1/chat/completions",
                        model_name="qwen3.6-27b", api_key="local",
                        transport="requests",
                        note="llama-server:8080，服务未常开，用前先启动"),
            ApiProvider(name="本地 bge-m3 嵌入", kind="embed", sort=6,
                        base_url="http://127.0.0.1:8890/v1/embeddings",
                        model_name="bge-m3", api_key="local",
                        transport="requests",
                        note="投标审查/RAG 语义检索用；当前全局嵌入模型"),
        ]
        skipped = [r.name for r in rows if not r.api_key]
        db.session.add_all(rows)
        db.session.commit()
        print(f"已登记 {len(rows)} 条")
        if skipped:
            print("注意，以下条目没读到 key（登记为空，需后台补填）:", "、".join(skipped))


if __name__ == "__main__":
    main()
