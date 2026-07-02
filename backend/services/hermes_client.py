"""Hermes API 客户端：把确认好的信息发给本机 Hermes(127.0.0.1:8645)，
由 Hermes 后台去 https://rd-web.mobimedical.cn 自动填写并提交审签。"""
import requests

HERMES_BASE = "http://127.0.0.1:8645"
TYPE_PATH = {
    "agency-agreement": "/api/agency-agreement",        # 代理协议审签
    "procurement-approval": "/api/procurement-approval",  # 采购项目审批
    "procurement-contract": "/api/procurement-contract",  # 采购合同审签
    "procurement-demand": "/api/procurement-demand",      # 采购需求审签表（暂不用）
}


def submit(task_type, task_id, action, data, callback_url=""):
    path = TYPE_PATH.get(task_type)
    if not path:
        raise ValueError(f"未知任务类型: {task_type}")
    r = requests.post(HERMES_BASE + path, json={
        "task_id": task_id, "action": action, "data": data, "callback_url": callback_url,
    }, timeout=15)
    r.raise_for_status()
    return r.json()


def status(task_id):
    r = requests.get(f"{HERMES_BASE}/api/status/{task_id}", timeout=15)
    r.raise_for_status()
    return r.json()
