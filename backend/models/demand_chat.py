# -*- coding: utf-8 -*-
"""采购需求 Agent 的对话记录。

黄新博 2026-08-20：「可以做成像微信一样的，有消息记录，能看到我和 agent 的对话，
可以直接把文件进行上传，并且直接告诉他怎么去干活」。

一条需求一串对话，存下来——下次打开还能看到上次聊到哪、传过什么、
它给过什么建议、你采纳了哪些。一次性弹窗那种问完就没了，没法追问也没法回看。
"""
from models import db


class DemandChatMessage(db.Model):
    __tablename__ = "demand_chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    demand_id = db.Column(db.Integer, index=True, nullable=False)
    # 哪张表的需求：政府采购(gov) / 院内竞选(internal)。两边共用这张消息表。
    demand_kind = db.Column(db.String(20), default="gov")

    role = db.Column(db.String(10), default="user")      # user / agent
    text = db.Column(db.Text, default="")

    # 这条消息带的附件：[{"name":..., "saved":..., "chars":n, "error":""}]
    files_json = db.Column(db.Text, default="[]")
    # 这条消息带来的资料原文。后续轮次要带上——不然人问「质保期多久」，
    # 它已经不记得上一轮传的文件了（实测第二轮就失忆）。
    material = db.Column(db.Text, default="")
    # agent 消息可能附带结构化建议：{"fields":{...}, "packages":[...]}
    suggestions_json = db.Column(db.Text, default="")
    # 人采纳了哪些（采纳后回写，界面上标出来）
    applied_json = db.Column(db.Text, default="")

    created_by = db.Column(db.String(50), default="")
    created_at = db.Column(db.String(30), default="")

    def to_dict(self):
        import json

        def _load(v, default):
            try:
                return json.loads(v) if v else default
            except Exception:                                # noqa: BLE001
                return default

        return {
            "id": self.id,
            "role": self.role or "user",
            "text": self.text or "",
            "files": _load(self.files_json, []),
            "suggestions": _load(self.suggestions_json, None),
            "applied": _load(self.applied_json, None),
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
        }
