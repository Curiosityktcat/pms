from . import db


class Law(db.Model):
    """法规库：政府采购相关法律法规 / 部门规章 / 规范性文件 / 政策解读 / 地方法规 等。
    数据来源：易采通法规库(law.ycait.com) 与 四川政府采购制度汇编 联网补全。"""
    __tablename__ = "laws"

    id = db.Column(db.Integer, primary_key=True)

    # 来源标识
    ycait_id = db.Column(db.Integer, index=True)          # law.ycait.com 的 id（web 来源为空）
    source = db.Column(db.String(20), default="ycait")     # ycait / web
    source_url = db.Column(db.String(400), default="")

    # 分类表头（照抄原站：法规库层次/颁布单位/颁布日期/实施日期/时效性/适用地区/条法类别）
    level = db.Column(db.String(60), default="", index=True)        # 法规库层次
    issue_unit = db.Column(db.String(120), default="")             # 颁布单位
    issue_date = db.Column(db.String(40), default="")             # 颁布日期
    implementation_date = db.Column(db.String(40), default="")    # 实施日期
    expiration_date = db.Column(db.String(40), default="")        # 失效日期
    timeliness = db.Column(db.String(20), default="", index=True)  # 时效性：有效/失效/废止
    region = db.Column(db.String(60), default="", index=True)      # 适用地区
    category = db.Column(db.String(200), default="")              # 条法类别
    law_number = db.Column(db.String(120), default="")           # 发文字号

    # 标题与正文
    title = db.Column(db.String(300), default="", index=True)
    alias_title = db.Column(db.String(200), default="")
    notify_title = db.Column(db.Text, default="")     # 公布令标题
    info_content = db.Column(db.Text, default="")     # 公布令正文/前言
    info_inscribe = db.Column(db.Text, default="")    # 署名
    full_text = db.Column(db.Text, default="")        # 全文（条文纯文本，供检索/LLM）
    body_json = db.Column(db.Text, default="[]")      # 结构化正文块 [{kind,text}]

    # 与四川政府采购制度汇编目录的对应（属于 145 项之一时填写）
    catalog_num = db.Column(db.Integer, index=True)   # 汇编序号 1..145
    catalog_category = db.Column(db.String(60), default="")  # 汇编大类

    created_at = db.Column(db.String(30), default="")

    def to_dict(self, full=False):
        d = {
            "id": self.id,
            "ycait_id": self.ycait_id,
            "source": self.source,
            "source_url": self.source_url,
            "level": self.level,
            "issue_unit": self.issue_unit,
            "issue_date": self.issue_date,
            "implementation_date": self.implementation_date,
            "expiration_date": self.expiration_date,
            "timeliness": self.timeliness,
            "region": self.region,
            "category": self.category,
            "law_number": self.law_number,
            "title": self.title,
            "alias_title": self.alias_title,
            "catalog_num": self.catalog_num,
            "catalog_category": self.catalog_category,
        }
        if full:
            d.update({
                "notify_title": self.notify_title,
                "info_content": self.info_content,
                "info_inscribe": self.info_inscribe,
                "full_text": self.full_text,
                "body_json": self.body_json,
            })
        return d
