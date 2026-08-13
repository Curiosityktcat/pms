# -*- coding: utf-8 -*-
"""官网公告存档：医院官网「招标采购信息」栏目挂过的公告。

PMS 2026 年 6 月才上线，之前所有院内竞选项目的公告只挂在官网上
（https://www.njyy.com.cn/News/lists/id/34.html）。这张表把官网公告抓回来存档，
挂到对应的采购项目上，补齐 PMS 上线前那段的挂网时间、开标时间等过程数据。

与 `announcements` 表的区别：那张是 PMS 自己起草、走审核流程的公告（有草稿态、驳回等）；
这张是**只读的历史存档**，来源是官网，不参与任何流程，也不允许在 PMS 里编辑。
按黄新博 2026-07-30 的要求，这些字段以官网为准。
"""
from models import db


class WebAnnouncement(db.Model):
    __tablename__ = "web_announcements"

    id = db.Column(db.Integer, primary_key=True)
    # 官网文章 id，唯一，重复抓取时按它去重
    site_id = db.Column(db.Integer, index=True, unique=True)
    url = db.Column(db.String(300), default="")
    title = db.Column(db.String(400), default="")

    ann_type = db.Column(db.String(30), index=True, default="")   # 院内竞选公告/更正公告/结果公示…
    publish_date = db.Column(db.String(20), index=True, default="")  # 挂网时间（官网列表页日期）
    bid_time = db.Column(db.String(30), default="")               # 开标 / 递交截止时间
    bid_place = db.Column(db.String(300), default="")
    doc_get_start = db.Column(db.String(20), default="")          # 获取采购文件起
    doc_get_end = db.Column(db.String(20), default="")            # 获取采购文件止

    project_number = db.Column(db.String(80), index=True, default="")  # 公告里写的编号
    project_name = db.Column(db.String(400), default="")               # 公告里写的名称（已去院名前缀）
    round_text = db.Column(db.String(20), default="")
    agency = db.Column(db.String(120), default="")
    method = db.Column(db.String(30), default="")
    budget_text = db.Column(db.String(200), default="")

    officer = db.Column(db.String(50), index=True, default="")    # 采购部经办人（四人之一）
    officer_basis = db.Column(db.String(120), default="")         # 怎么判出来的，便于复核
    purchaser_phone = db.Column(db.String(60), default="")
    dept_contact = db.Column(db.String(60), default="")
    agency_contact = db.Column(db.String(60), default="")

    winner = db.Column(db.String(200), default="")                # 结果类公告才有
    win_amount = db.Column(db.String(100), default="")

    # 与 PMS 项目的挂钩
    project_id = db.Column(db.Integer, index=True, nullable=True)
    match_how = db.Column(db.String(40), default="")              # 靠什么匹配上的
    needs_check = db.Column(db.Integer, default=0)                # 1=需人工确认

    body = db.Column(db.Text, default="")                         # 正文留档，便于回溯
    created_at = db.Column(db.String(30), default="")

    def to_dict(self, with_body=False):
        d = {
            "id": self.id, "site_id": self.site_id, "url": self.url or "",
            "title": self.title or "", "ann_type": self.ann_type or "",
            "publish_date": self.publish_date or "", "bid_time": self.bid_time or "",
            "bid_place": self.bid_place or "",
            "doc_get_start": self.doc_get_start or "", "doc_get_end": self.doc_get_end or "",
            "project_number": self.project_number or "", "project_name": self.project_name or "",
            "round_text": self.round_text or "", "agency": self.agency or "",
            "method": self.method or "", "budget_text": self.budget_text or "",
            "officer": self.officer or "", "officer_basis": self.officer_basis or "",
            "purchaser_phone": self.purchaser_phone or "",
            "dept_contact": self.dept_contact or "", "agency_contact": self.agency_contact or "",
            "winner": self.winner or "", "win_amount": self.win_amount or "",
            "project_id": self.project_id, "match_how": self.match_how or "",
            "needs_check": int(self.needs_check or 0),
        }
        if with_body:
            d["body"] = self.body or ""
        return d
