"""按《2026-8-15 Pms系统的人员和权限设计》录入全院科室与科室负责人。

口径（来自该文件第 1、2 节）：
  · **所有科室都是需求科室**，都可以提采购需求 —— 所以不再单设「需求科室」标记。
  · **所有行后科室都是归口管理科室，唯独采购部不是**（采管分离，岗位不兼容）。
  · 流程：需求科室提需求 → 归口管理科室汇总审批 → 采购部执行采购 →
    合同/采购结果回归口 → 归口与需求科室共同履约验收 → 归口科室报销。

新增两列：
  dept_type  行后 / 临床医技      （文件里明确标了「（行后）」的即行后）
  head_name  科室主要负责人姓名   （科室账号登录后右上角显示「科室+人名」要用）

**不做没有实据的合并**：现有字典里的「预保科」「院办」在这份名单里没有对应条目，
可能是改名也可能是我不知道的科室，一律保留原条目并在 note 里写明待人工确认——
合错了会让 A 科室看见 B 科室的项目（见 services/dept.py 顶部的口径说明）。
"""
import sys

sys.path.insert(0, ".")

from sqlalchemy import text

from app import create_app
from models import db
from models.dept import Dept

# (code, 现用名, 别名, category, dept_type, 负责人, 备注)
# category 沿用既有取值：归口/实施/职能/监督/法务，可多值逗号分隔。
ROSTER = [
    # ── 行后（行政后勤）：除采购部外都是归口管理科室 ──────────────────
    ("DB",     "党委办公室", "党办", "归口", "行后", "刘小瑕", ""),
    ("XZB",    "行政办公室", "行政办", "归口", "行后", "范文江", ""),
    ("CGB",    "采购部", "采购管理部", "实施", "行后", "曾旌城",
     "采管分离：采购部是采购实施科室，不作为归口管理科室"),
    ("YWK",    "医务部", "医务科", "归口", "行后", "王毅", ""),
    ("HLB",    "护理部", "", "归口", "行后", "刘晓霞", ""),
    ("FWB",    "法务部", "医患沟通办公室", "归口,法务", "行后", "赵坤", ""),
    ("KJK",    "科教科", "", "归口", "行后", "徐锡", ""),
    ("ZKB",    "医疗质量管理控制办公室", "质控办", "归口", "行后", "曹建", ""),
    ("TW",     "团委", "", "归口", "行后", "邹杨", ""),
    ("JWB",    "纪委办公室", "纪委办", "监督", "行后", "陈凯", ""),
    ("GHB",    "工会办", "工会办公室", "归口", "行后", "谢英", "谢英一人担两职（另兼离退休办）"),
    ("SJK",    "审计科", "", "归口,监督", "行后", "刘堇羽", ""),
    ("XCK",    "宣传统战部", "宣传科,宣传统战部（文明办）,宣传统战社工部,文明办",
     "归口", "行后", "邓敏", ""),
    ("RSK",    "人事科", "", "归口", "行后", "唐静", ""),
    ("LTXB",   "离退休管理与服务办公室", "离退休办", "归口", "行后", "谢英",
     "谢英一人担两职（另兼工会办）"),
    ("CWK",    "财务科", "财务部", "职能", "行后", "邓卉", ""),
    ("YBB",    "医保办", "医保办公室", "归口", "行后", "郑义",
     "与既有「预保科(YBK)」不是同一科室，勿合并"),
    ("YGK",    "医院感染管理科", "院感科", "归口", "行后", "邹安娜", ""),
    ("GGWSK",  "公共卫生科", "", "归口", "行后", "李其俊", ""),
    ("GGSYB",  "公共事业发展部", "分级诊疗办公室,公共事业发展部（分级诊疗办公室）",
     "归口", "行后", "刘礼", ""),
    ("XXK",    "信息科", "信息中心", "归口", "行后", "雷强", ""),
    ("BAGLK",  "病案管理科", "病案科", "归口", "行后", "高健", ""),
    ("ZWK",    "总务科", "", "归口", "行后", "李铂", ""),
    ("SBK",    "医学装备部", "设备科", "归口", "行后", "甘锐", ""),
    ("JJK",    "基建科", "", "归口", "行后", "吴晓川", ""),
    ("BWK",    "保卫科", "", "归口", "行后", "吴选飞", ""),
    ("YYGLB",  "运营管理部", "运营部", "职能", "行后", "刘韦利", ""),
    ("YJK",    "药剂科", "", "归口", "行后", "罗玲艳", "罗玲艳一人担两职（另兼临床试验机构办）"),
    ("LCSYB",  "临床试验机构办公室", "临床试验机构办", "归口", "行后", "罗玲艳",
     "罗玲艳一人担两职（另兼药剂科）"),

    # ── 临床、医技：都是需求科室 ────────────────────────────────────
    ("PWGDYP", "普外科（肝胆胰脾）", "", "需求", "临床医技", "谢飞", ""),
    ("PWJZRX", "普外科（甲状腺乳腺）、血管外科", "血管外科", "需求", "临床医技", "李伟", ""),
    ("PWWCXE", "普外科（胃肠）、小儿外科", "小儿外科", "需求", "临床医技", "张旭", ""),
    ("MZSSZX", "麻醉手术中心", "", "需求", "临床医技", "杨勇", ""),
    ("JZK",    "急诊科", "", "需求", "临床医技", "王宗林", ""),
    ("ZZYXK",  "重症医学科", "ICU", "需求", "临床医技", "段莉莉", ""),
    ("JZCSGK", "脊柱、创伤骨科", "", "需求", "临床医技", "黄凯", ""),
    ("GJCSGK", "关节、创伤骨科", "", "需求", "临床医技", "涂宏亮", ""),
    ("SJWK",   "神经外科", "", "需求", "临床医技", "刘丛", ""),
    ("XXWK",   "胸心外科", "", "需求", "临床医技", "李季", ""),
    ("MNWK",   "泌尿外科", "", "需求", "临床医技", "陈智彬", ""),
    ("KQK",    "口腔科", "", "需求", "临床医技", "孙良丰", ""),
    ("EBYHK",  "耳鼻咽喉头颈外科", "耳鼻喉科", "需求", "临床医技", "彭利", ""),
    ("YANK",   "眼科", "", "需求", "临床医技", "刘刚", ""),
    ("XYNK",   "血液内科", "", "需求", "临床医技", "程红", ""),
    ("FUK",    "妇科", "", "需求", "临床医技", "黄小琴", ""),
    ("CHK",    "产科", "", "需求", "临床医技", "江梅", ""),
    ("MRZXSSK", "美容整形烧伤科", "", "需求", "临床医技", "银西洋", ""),
    ("ERK",    "儿科", "", "需求", "临床医技", "黄晓玲", ""),
    ("HXWZ",   "呼吸与危重症医学科", "呼吸内科", "需求", "临床医技", "李兴明", ""),
    ("SBNK",   "肾病内科", "", "需求", "临床医技", "夏林", ""),
    ("KFYXK",  "康复医学科", "康复科", "需求", "临床医技", "沈晓聪", ""),
    ("XXGNK",  "心血管内科", "", "需求", "临床医技", "廖锐", ""),
    ("QKYXK",  "全科医学科", "", "需求", "临床医技", "余秀", "余秀一人担两职（另兼健康管理科）"),
    ("XHNK",   "消化内科", "", "需求", "临床医技", "钟玉全", ""),
    ("ZLYK",   "肿瘤一科", "", "需求", "临床医技", "倪亚非", ""),
    ("ZLEK",   "肿瘤二科", "", "需求", "临床医技", "黄思思", ""),
    ("FSMYK",  "风湿免疫科", "", "需求", "临床医技", "熊安吉", ""),
    ("ZXYJHK", "中西医结合科", "", "需求", "临床医技", "肖忠英", ""),
    ("GRK",    "感染科", "", "需求", "临床医技", "陈炘", ""),
    ("PFMRK",  "皮肤美容科", "皮肤科", "需求", "临床医技", "胡于良", ""),
    ("LNYXK",  "老年医学科", "", "需求", "临床医技", "石宗民", ""),
    ("SJNK",   "神经内科", "", "需求", "临床医技", "周立", ""),
    ("NFMK",   "内分泌科", "", "需求", "临床医技", "刘斌", ""),
    ("MZB",    "门诊部", "", "需求", "临床医技", "王信春", "王信春一人担两职（另兼疼痛科）"),
    ("TTK",    "疼痛科", "", "需求", "临床医技", "王信春", "王信春一人担两职（另兼门诊部）"),
    ("GYS",    "供应室", "消毒供应中心", "需求", "临床医技", "刘菊", ""),
    ("JKGLK",  "健康管理科", "体检中心", "需求", "临床医技", "余秀", "余秀一人担两职（另兼全科医学科）"),
    ("SXK",    "输血科", "", "需求", "临床医技", "黄波", ""),
    ("HYXK",   "核医学科", "", "需求", "临床医技", "廖林森", ""),
    ("BLK",    "病理科", "", "需求", "临床医技", "刘清松", ""),
    ("CSYXK",  "超声医学科", "超声科", "需求", "临床医技", "张亚萍", ""),
    ("JYK",    "检验科", "", "需求", "临床医技", "钟晓明", ""),
    ("FSK",    "放射科", "", "需求", "临床医技", "陈希奎", ""),
    ("NJZX",   "内镜中心", "", "需求", "临床医技", "张方宇", ""),
    ("JRSSS",  "介入手术室", "", "需求", "临床医技", "袁权", ""),
]

# 名单里没有、但字典里已存在的老条目：保留，只标注待确认，绝不擅自合并或停用。
KEEP_WITH_NOTE = {
    "YBK": "2026-08-15 全院科室名单里没有「预保科」，可能已并入公共卫生科或改名，待人工确认。勿与医保办(YBB)合并。",
    "YB":  "2026-08-15 全院科室名单里没有「院办」，可能即行政办公室(XZB)，待人工确认后再决定是否合并。",
    "ZCGLZ": "资产管理组来自采购管理内控（采购职能科室），不在科室负责人名单内，负责人待补。",
}


def ensure_columns():
    """给 depts 补 dept_type / head_name 两列（沿用 app.py 的 PRAGMA + ALTER 幂等写法）。"""
    with db.engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(depts)"))}
        for col, typedef in (("dept_type", "TEXT DEFAULT ''"), ("head_name", "TEXT DEFAULT ''")):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE depts ADD COLUMN {col} {typedef}"))
                conn.commit()
                print(f"  depts.{col} 已补")


def main():
    app = create_app()
    with app.app_context():
        ensure_columns()
        added, updated = [], []
        for i, (code, name, aliases, category, dtype, head, note) in enumerate(ROSTER):
            row = db.session.execute(db.select(Dept).filter_by(code=code)).scalar_one_or_none()
            if row is None:
                db.session.add(Dept(code=code, name=name, aliases=aliases, category=category,
                                    dept_type=dtype, head_name=head, note=note,
                                    sort_no=i, active=1))
                added.append(f"{name}({code})")
                continue
            changes = []
            for field, value in (("name", name), ("category", category),
                                 ("dept_type", dtype), ("head_name", head), ("sort_no", i)):
                if (getattr(row, field) or "") != value and value != "":
                    changes.append(f"{field}:{getattr(row, field) or '空'}→{value}")
                    setattr(row, field, value)
            # 别名只增不减：老别名是历史项目匹配的依据，删了就看不见老项目
            old_aliases = [a for a in (row.aliases or "").replace("、", ",").split(",") if a.strip()]
            merged = list(dict.fromkeys([a.strip() for a in old_aliases + aliases.split(",") if a.strip()]))
            if ",".join(merged) != (row.aliases or ""):
                changes.append("aliases+")
                row.aliases = ",".join(merged)
            if note and note not in (row.note or ""):
                row.note = ((row.note or "") + " " + note).strip()
                changes.append("note+")
            if changes:
                updated.append(f"{name}({code}): {'; '.join(changes)}")
        for code, note in KEEP_WITH_NOTE.items():
            row = db.session.execute(db.select(Dept).filter_by(code=code)).scalar_one_or_none()
            if row is not None and note not in (row.note or ""):
                row.note = ((row.note or "") + " " + note).strip()
                row.sort_no = 900
                updated.append(f"{row.name}({code}): 标注待确认")
        db.session.commit()

        print(f"\n新增 {len(added)} 个科室：", "、".join(added) if added else "无")
        print(f"更新 {len(updated)} 个科室：")
        for u in updated:
            print("   ", u)
        rows = db.session.execute(db.select(Dept).order_by(Dept.sort_no, Dept.id)).scalars().all()
        hh = sum(1 for d in rows if (d.dept_type or "") == "行后")
        lc = sum(1 for d in rows if (d.dept_type or "") == "临床医技")
        print(f"\n共 {len(rows)} 个科室：行后 {hh}、临床医技 {lc}、未分类 {len(rows) - hh - lc}")
        print("未填负责人的：", "、".join(d.name for d in rows if not (d.head_name or "")) or "无")


if __name__ == "__main__":
    main()
