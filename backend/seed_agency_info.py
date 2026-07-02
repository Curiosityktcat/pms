"""一次性录入 8 家代理机构的 法人/联系方式/地址（按 code 匹配，已存在则更新）。"""
import sys
sys.path.insert(0, "/home/huangxb/pms/backend")
from app import create_app
from models import db
from models.agency import Agency

DATA = {
    "ZX": ("四川知行招标代理有限公司", "银钒霖", "0832-2029668", "四川省内江市东兴区万达中心2112-2115号", 0),
    "ZZ": ("内江中洲工程项目管理有限公司", "周丽萍", "13882007116", "内江市东兴区中兴路1104号5幢1单元207号（上海花园）", 0),
    "ZJ": ("四川中锦招标代理有限公司", "何根炜", "0832-2242423", "内江市汉安大道西段927号40幢2楼1号、2号", 0),
    "SJ": ("四川尚璟招标代理有限责任公司", "余尚英", "0832-2267533", "内江市东兴区兰桂大道222号负一层3号、4号、5号、6号、7号", 0),
    "HX": ("四川华询工程管理有限责任公司", "唐国英", "0832-2035990", "内江市东兴区北环路四季康城12号楼【幢】无单元2层2-5号", 0),
    "SY": ("四川三盈招标代理有限公司", "余勇", "0832-2111314", "内江市东兴区胜利路666号1栋2单元A区7层6号（汉安大道传化广场锦城A区）", 0),
    "CJ": ("内江市川交公路勘察设计有限公司", "田玉冲", "17313721737 0832-2223383", "四川省内江市东兴区梧桐路1号二幢2单元27楼23号", 0),
    "ZC": ("内江市政府采购中心", "卿伟", "0832-2048628", "四川省内江市东兴区兰桂大道377号", 1),
}

app = create_app()
with app.app_context():
    for code, (name, rep, phone, addr, central) in DATA.items():
        a = db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none()
        if not a:
            print("缺机构:", code, name, "(跳过)")
            continue
        a.legal_rep, a.phone, a.address, a.is_central = rep, phone, addr, central
        print(f"  {code} {a.name} <- 法人{rep} / {phone} / {addr[:14]}…")
    db.session.commit()
    print("== 录入完成，复核 ==")
    for a in db.session.execute(db.select(Agency).order_by(Agency.is_central, Agency.rotation_seq)).scalars().all():
        print(f"  {a.code} {a.name} | 法人={a.legal_rep} | 电话={a.phone} | 集采={a.is_central}")
