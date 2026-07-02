from . import db


class SupervisionChannel(db.Model):
    """全国政府采购质疑/投诉受理 与 公共资源交易行政监督 渠道库。

    对应招标文件 2.8《询问、质疑和投诉》：
      - 政府采购网(ccgp-*) = 各地财政部门·政府采购监督管理入口，质疑/投诉范本与受理联系方式在此公布；
      - 公共资源交易平台    = 交易过程行政监督(公共资源交易监管)入口。
    数据来源：知乎《全国最全招投标网站》(zhuanlan.zhihu.com/p/697136714)，按地区整理。
    """
    __tablename__ = "supervision_channels"

    id = db.Column(db.Integer, primary_key=True)

    region = db.Column(db.String(40), default="", index=True)        # 简称：四川/北京/广西
    region_full = db.Column(db.String(60), default="")               # 全称：广西壮族自治区
    level = db.Column(db.String(20), default="", index=True)         # 国家级/直辖市/省级/自治区
    org_type = db.Column(db.String(40), default="", index=True)      # 政府采购网 / 公共资源交易平台
    channel = db.Column(db.String(80), default="")                   # 渠道用途说明
    name = db.Column(db.String(120), default="", index=True)         # 机构/平台名称
    url = db.Column(db.String(400), default="")                      # 官网链接

    source = db.Column(db.String(60), default="")                    # 数据来源标识
    source_url = db.Column(db.String(400), default="")               # 来源页 URL

    # 网页快照（"下载下来"：抓取各渠道首页存档，便于离线核对/校验链接有效性）
    page_title = db.Column(db.String(300), default="")               # 抓到的网页 <title>
    http_status = db.Column(db.Integer)                              # 抓取 HTTP 状态码(0=失败)
    snapshot_file = db.Column(db.String(200), default="")            # 本机快照文件名(snapshots/ 下)
    fetched_at = db.Column(db.String(30), default="")                # 抓取时间
    created_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "region": self.region,
            "region_full": self.region_full,
            "level": self.level,
            "org_type": self.org_type,
            "channel": self.channel,
            "name": self.name,
            "url": self.url,
            "source": self.source,
            "source_url": self.source_url,
            "page_title": self.page_title,
            "http_status": self.http_status,
            "snapshot_file": self.snapshot_file,
            "fetched_at": self.fetched_at,
        }
