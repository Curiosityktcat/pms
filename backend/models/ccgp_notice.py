from models import db


class CcgpNotice(db.Model):
    """四川政府采购网抓取的公告（中标公告 / 合同公告）。

    数据来源：www.ccgp-sichuan.gov.cn 的 gpcms 开放接口
    （列表 selectInfoMoreChannel + 详情 getInfoById），由 Playwright 驱动抓取。
    """
    __tablename__ = "ccgp_notices"

    id          = db.Column(db.String(64), primary_key=True)   # 网站公告 id
    notice_type = db.Column(db.String(20), index=True)         # 中标公告 | 合同公告
    title       = db.Column(db.Text, default="")
    project_no  = db.Column(db.String(120), default="")        # 项目编号（正文抽取）
    purchaser   = db.Column(db.String(200), default="")        # 采购人
    agency      = db.Column(db.String(200), default="")        # 代理机构
    region      = db.Column(db.String(60), default="")         # 地区
    win_company = db.Column(db.String(200), default="")        # 中标人/供应商（正文抽取）
    amount      = db.Column(db.String(60), default="")         # 中标/合同金额（正文抽取）
    notice_time = db.Column(db.String(30), default="", index=True)  # 公告时间
    content     = db.Column(db.Text, default="")               # 正文纯文本
    source_url  = db.Column(db.Text, default="")               # 原文链接
    first_seen  = db.Column(db.String(30), default="")
    updated_at  = db.Column(db.String(30), default="")

    def to_dict(self, with_content=False):
        d = {
            "id": self.id,
            "notice_type": self.notice_type or "",
            "title": self.title or "",
            "project_no": self.project_no or "",
            "purchaser": self.purchaser or "",
            "agency": self.agency or "",
            "region": self.region or "",
            "win_company": self.win_company or "",
            "amount": self.amount or "",
            "notice_time": self.notice_time or "",
            "source_url": self.source_url or "",
            "updated_at": self.updated_at or "",
        }
        if with_content:
            d["content"] = self.content or ""
        return d
