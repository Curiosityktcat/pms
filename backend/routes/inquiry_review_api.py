"""询议价评审 API（模块8.1）  —  /api/inquiry-reviews、/api/inquiries/<lid>/review

业务规则（经办人口述，2026-06）：
- 议价：≥1 家通过资格+符合性审查即可与供应商确认最终报价，最低价中选；
  全部不通过则废标并开下一轮。
- 询价：第一轮通过资格+符合性审查必须满 3 家，否则直接废标；
  第二轮起经办人有自由裁量权，不足 3 家可转为院内议价（评审办法改"院内议价"），
  也可继续废标开下一轮。第一轮不允许转议价。
- 每轮评审完成后按用户的评定标报告 Excel 模板出记录，打印签字。
"""
import datetime
import os
import shutil
import time

from flask import Blueprint, request, session, jsonify, send_file

from models import db
from models.inquiry_letter import InquiryLetter
from models.inquiry_supplier import InquirySupplier
from models.inquiry_review import InquiryReview, InquirySupplierFile
from models.project import Project
from routes.utils import login_required, can_view_project

HERE = os.path.dirname(os.path.abspath(__file__))
PMS_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
RESP_DIR = os.path.join(PMS_ROOT, '询价附件', '响应')
ATTACH_DIR = os.path.join(PMS_ROOT, '询价附件', '上传')
ATTACH_ALLOWED = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.zip', '.rar'}

bp = Blueprint("inquiry_review", __name__)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _today():
    return datetime.date.today().isoformat()


def _scoped_letter(lid):
    """取询/议价函并做归属校验（officer 本人经办 / agency 本机构 / 助理·负责人·管理员）。
    返回 (letter, error)；error 非空时应直接 return。"""
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return None, (jsonify({"ok": False, "error": "函件不存在"}), 404)
    if not can_view_project(db.session.get(Project, letter.project_id)):
        return None, (jsonify({"ok": False, "error": "无权访问该询/议价评审"}), 403)
    return letter, None


def _round_no(letter: InquiryLetter) -> int:
    """该函件是同项目的第几轮邀请。

    默认按函件创建顺序逐个 +1；带 round_no 覆盖的函件（同轮"询价废标转议价"）
    用覆盖值且不推进计数 —— 例如：询价①=1、询价②=2(废标)、议价(转,覆盖)=2、
    再开下一轮询价=3。
    """
    letters = db.session.execute(
        db.select(InquiryLetter)
        .filter_by(project_id=letter.project_id)
        .order_by(InquiryLetter.id)
    ).scalars().all()
    cur = 0
    for lt in letters:
        n = lt.round_no if lt.round_no else cur + 1
        if lt.id == letter.id:
            return n
        cur = max(cur, n)
    return 1


def _deadline_passed(letter: InquiryLetter) -> bool:
    return bool(letter.deadline) and _today() >= letter.deadline


def _suppliers(lid):
    return db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=lid).order_by(InquirySupplier.id)
    ).scalars().all()


def _pass_count(sups) -> int:
    """通过资格性+符合性审查的家数（只算已递交响应的）"""
    return sum(1 for s in sups
               if s.responded and s.qual_pass == "通过" and s.conform_pass == "通过")


def _fmt_amount(v) -> str:
    if v is None:
        return ""
    s = f"{v:g}" if isinstance(v, float) else str(v)
    return f"{s}元"


def _review_dict(review, letter, sups=None):
    d = review.to_dict()
    d["letter_type"] = letter.type
    d["letter_status"] = letter.status
    d["deadline"] = letter.deadline
    d["deadline_passed"] = _deadline_passed(letter)
    # 第一轮询价不允许转议价；第二轮起经办人自由裁量
    d["method_switchable"] = not (letter.type == "询价" and (review.round_no or 1) <= 1)
    if sups is None:
        sups = _suppliers(letter.id)
    d["suppliers"] = [s.to_dict() for s in sups]
    d["pass_count"] = _pass_count(sups)
    d["responded_count"] = sum(1 for s in sups if s.responded)
    files = db.session.execute(
        db.select(InquirySupplierFile).filter_by(inquiry_id=letter.id)
        .order_by(InquirySupplierFile.id)
    ).scalars().all()
    by_sup = {}
    for f in files:
        by_sup.setdefault(f.supplier_id, []).append(f.to_dict())
    d["supplier_files"] = by_sup
    return d


# ─────────────────────────────────────────────────────────────────
# 模块 8.1 列表：待评审 / 已评审
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiry-reviews", methods=["GET"])
@login_required
def list_reviews():
    letters = db.session.execute(
        db.select(InquiryLetter).order_by(InquiryLetter.id.desc())
    ).scalars().all()
    reviews = {r.inquiry_id: r for r in db.session.execute(
        db.select(InquiryReview)).scalars().all()}

    rows = []
    for l in letters:
        rv = reviews.get(l.id)
        # 待评审 = 已发出（进行中）；已评审 = 评审记录已完成
        if l.status == "待办" and not rv:
            continue
        proj = db.session.get(Project, l.project_id)
        # 数据级隔离：经办人只看本人项目、代理只看本机构（与项目列表口径一致）
        if not can_view_project(proj):
            continue
        sups = _suppliers(l.id)
        rows.append({
            "inquiry_id": l.id,
            "project_id": l.project_id,
            "project_name": proj.name if proj else "",
            "project_number": proj.number if proj else "",
            "type": l.type,
            "title": l.title,
            "deadline": l.deadline,
            "deadline_passed": _deadline_passed(l),
            "letter_status": l.status,
            "created_at": l.created_at,
            "round_no": rv.round_no if rv else _round_no(l),
            "supplier_count": len(sups),
            "responded_count": sum(1 for s in sups if s.responded),
            "early_open": rv.early_open if rv else 0,
            "review_status": rv.status if rv else "",
            "result_type": rv.result_type if rv else "",
            "method": rv.method if rv else ("院内询价" if l.type == "询价" else "院内议价"),
            "completed_at": rv.completed_at if rv else "",
        })
    return jsonify({"ok": True, "data": rows})


# ─────────────────────────────────────────────────────────────────
# 评审记录 get-or-create / 保存 / 完成 / 撤回
# ─────────────────────────────────────────────────────────────────

_BID_OPEN_TMPL = (
    "（一）按照采购文件规定的时间，于  年  月  日在  进行 。\n"
    "（二）递交响应文件截止时间：{deadline}（北京时间），共收到 {n} 家供应商的响应文件。\n"
    "（三）由 主持， 进行现场监督。\n"
    "（四）开标过程中，由供应商代表对响应文件的密封情况进行了检查。\n"
    "（五）开标过程顺利。"
)


def _build_review(letter):
    """按函件 + 项目立项快照初始化一条评审记录（未 commit）。"""
    proj = db.session.get(Project, letter.project_id)
    sups = _suppliers(letter.id)
    now = _now()
    return InquiryReview(
        inquiry_id     = letter.id,
        project_id     = letter.project_id,
        round_no       = _round_no(letter),
        project_name   = proj.name if proj else "",
        project_number = (proj.number or "") if proj else "",
        package_no     = "/",
        content        = letter.detail or (proj.content if proj else "") or "",
        budget         = _fmt_amount(proj.amount) if proj else "",
        review_date    = "",
        location       = "审计科",
        method         = "院内询价" if letter.type == "询价" else "院内议价",
        bid_open_info  = _BID_OPEN_TMPL.format(
            deadline=letter.deadline or "    ", n=len(sups) or " "),
        created_by     = session.get("display_name", ""),
        created_at     = now,
        updated_at     = now,
    )


@bp.route("/api/inquiries/<int:lid>/review", methods=["GET"])
@login_required
def get_review(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr

    review = db.session.execute(
        db.select(InquiryReview).filter_by(inquiry_id=lid)
    ).scalar_one_or_none()
    if not review:
        if letter.status == "待办":
            return jsonify({"ok": False, "error": "函件尚未发出，不能评审"}), 400
        if not _deadline_passed(letter):
            # 截止前不自动开启：须经办人「提前开启评审」（见 /review/early-open）
            return jsonify({"ok": False, "error": f"递交截止日期（{letter.deadline or '未填写'}）未到。"
                                                  "若供应商文件已齐，可由经办人「提前开启评审」。"}), 400
        review = _build_review(letter)
        db.session.add(review)
        db.session.commit()
    return jsonify({"ok": True, "data": _review_dict(review, letter)})


@bp.route("/api/inquiries/<int:lid>/review/early-open", methods=["POST"])
@login_required
def early_open_review(lid):
    """截止日期未到时，由经办人确认「提前开启评审」（供应商文件已齐）。
    仅 officer（项目经办人）角色可操作；记录确认人/时间。"""
    if session.get("role") != "officer":
        return jsonify({"ok": False, "error": "仅经办人可确认提前开启评审"}), 403

    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    if letter.status == "待办":
        return jsonify({"ok": False, "error": "函件尚未发出，不能评审"}), 400

    review = db.session.execute(
        db.select(InquiryReview).filter_by(inquiry_id=lid)
    ).scalar_one_or_none()
    if review:
        return jsonify({"ok": True, "message": "评审已开启",
                        "data": _review_dict(review, letter)})
    if _deadline_passed(letter):
        return jsonify({"ok": False, "error": "截止日期已过，无需提前，请直接进入评审"}), 400

    now = _now()
    review = _build_review(letter)
    review.early_open    = 1
    review.early_open_by = session.get("display_name", "")
    review.early_open_at = now
    db.session.add(review)
    db.session.commit()
    return jsonify({"ok": True, "message": "已提前开启评审",
                    "data": _review_dict(review, letter)})


_REVIEW_FIELDS = (
    "project_name", "project_number", "package_no", "content", "budget",
    "review_date", "location", "method", "result_type", "result_text",
    "remark", "review_place", "committee", "bid_open_info",
)
_SUP_REVIEW_FIELDS = (
    "quote_amount", "quote_date", "quote_note",
    "qual_pass", "conform_pass", "final_price", "review_rank", "fail_reason",
)


def _apply_supplier_rows(lid, rows):
    sups = {s.id: s for s in _suppliers(lid)}
    for row in rows:
        s = sups.get(row.get("id"))
        if not s:
            continue
        for f in _SUP_REVIEW_FIELDS:
            if f in row:
                setattr(s, f, row[f])
        name = row.get("supplier_name")
        if name is not None and str(name).strip():
            s.supplier_name = str(name).strip()
        if "responded" in row:
            s.responded = 1 if row["responded"] else 0


@bp.route("/api/inquiries/<int:lid>/review", methods=["PUT"])
@login_required
def save_review(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    review = db.session.execute(
        db.select(InquiryReview).filter_by(inquiry_id=lid)
    ).scalar_one_or_none()
    if not letter or not review:
        return jsonify({"ok": False, "error": "评审记录不存在"}), 404
    if review.status == "已完成":
        return jsonify({"ok": False, "error": "评审已完成，如需修改请先撤回"}), 400

    data = request.get_json(force=True) or {}
    if (data.get("method") == "院内议价" and letter.type == "询价"
            and (review.round_no or 1) <= 1):
        return jsonify({"ok": False, "error": "询价项目第一轮不允许转为院内议价"}), 400

    for f in _REVIEW_FIELDS:
        if f in data:
            setattr(review, f, data[f])
    review.updated_at = _now()

    _apply_supplier_rows(lid, data.get("suppliers", []))
    db.session.commit()
    return jsonify({"ok": True, "data": _review_dict(review, letter)})


@bp.route("/api/inquiries/<int:lid>/review/complete", methods=["POST"])
@login_required
def complete_review(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    review = db.session.execute(
        db.select(InquiryReview).filter_by(inquiry_id=lid)
    ).scalar_one_or_none()
    if not letter or not review:
        return jsonify({"ok": False, "error": "评审记录不存在"}), 404
    if review.status == "已完成":
        return jsonify({"ok": False, "error": "评审已完成"}), 400

    data = request.get_json(force=True) or {}
    result_type = data.get("result_type") or review.result_type
    if result_type not in ("中选", "废标"):
        return jsonify({"ok": False, "error": "请先选择评审结果（中选 / 废标）"}), 400

    sups = _suppliers(lid)
    responded = [s for s in sups if s.responded]
    passed = [s for s in responded
              if s.qual_pass == "通过" and s.conform_pass == "通过"]
    # 已递交响应的供应商必须有审查结论才能出中选结果（未响应的不要求）
    unfilled = [s for s in responded if not s.qual_pass or not s.conform_pass]
    if result_type == "中选" and unfilled:
        names = "、".join(s.supplier_name or f"#{s.id}" for s in unfilled[:5])
        return jsonify({"ok": False, "error": f"以下已响应供应商的资格性/符合性审查结论未填写：{names}"}), 400

    need = 3 if review.method == "院内询价" else 1
    if result_type == "中选":
        if len(passed) < need:
            return jsonify({
                "ok": False,
                "error": f"{review.method}要求通过资格性+符合性审查的供应商不少于 {need} 家，"
                         f"当前仅 {len(passed)} 家，只能废标"
                         + ("或转为院内议价（第二轮起）" if review.method == "院内询价" else ""),
            }), 400
        winner_id = data.get("winner_supplier_id")
        winner = next((s for s in passed if s.id == winner_id), None)
        if not winner:
            return jsonify({"ok": False, "error": "请在通过审查的供应商中选择中选供应商"}), 400
        for s in sups:
            s.is_selected = 1 if s.id == winner.id else 0
        if not (review.result_text or "").strip():
            price = winner.final_price or _fmt_amount(winner.quote_amount)
            review.result_text = f"{winner.supplier_name}以{price}价格成交。"
    else:  # 废标
        for s in sups:
            s.is_selected = 0
        if not (review.result_text or "").strip():
            if review.method == "院内询价":
                review.result_text = "有效供应商不足三家，故废标。"
            else:
                review.result_text = "无供应商通过资格性及符合性审查，故废标。"

    now = _now()
    review.result_type  = result_type
    review.status       = "已完成"
    review.completed_by = session.get("display_name", "")
    review.completed_at = now
    review.updated_at   = now
    letter.status       = "已完成"
    letter.updated_at   = now
    db.session.commit()
    return jsonify({"ok": True, "message": f"评审完成：{result_type}",
                    "data": _review_dict(review, letter, sups)})


@bp.route("/api/inquiries/<int:lid>/review/reopen", methods=["POST"])
@login_required
def reopen_review(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    review = db.session.execute(
        db.select(InquiryReview).filter_by(inquiry_id=lid)
    ).scalar_one_or_none()
    if not letter or not review:
        return jsonify({"ok": False, "error": "评审记录不存在"}), 404
    if review.status != "已完成":
        return jsonify({"ok": False, "error": "评审尚未完成，无需撤回"}), 400
    # 项目已归档则锁定，不可再撤回修改评审
    from models.project import Project as _Proj
    _proj = db.session.get(_Proj, letter.project_id)
    if _proj is not None and _proj.status == "已归档":
        return jsonify({"ok": False, "error": "项目已归档，评审不可再修改"}), 400
    # 已开下一轮则不允许撤回，防破坏轮次链
    newer = db.session.execute(
        db.select(InquiryLetter.id)
        .filter(InquiryLetter.project_id == letter.project_id,
                InquiryLetter.id > letter.id)
    ).first()
    if newer:
        return jsonify({"ok": False, "error": "该项目已开启下一轮，不能撤回本轮评审"}), 400

    review.status       = "草稿"
    review.completed_by = ""
    review.completed_at = ""
    review.updated_at   = _now()
    letter.status       = "进行中"
    letter.updated_at   = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回，可继续修改",
                    "data": _review_dict(review, letter)})


# ─────────────────────────────────────────────────────────────────
# 废标后一键开下一轮（复制本轮函件为新的待办件）
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/next-round", methods=["POST"])
@login_required
def next_round(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    review = db.session.execute(
        db.select(InquiryReview).filter_by(inquiry_id=lid)
    ).scalar_one_or_none()
    if not letter:
        return jsonify({"ok": False, "error": "函件不存在"}), 404
    if not review or review.status != "已完成" or review.result_type != "废标":
        return jsonify({"ok": False, "error": "仅本轮评审完成且废标后才能开下一轮"}), 400
    newer = db.session.execute(
        db.select(InquiryLetter.id)
        .filter(InquiryLetter.project_id == letter.project_id,
                InquiryLetter.id > letter.id)
    ).first()
    if newer:
        return jsonify({"ok": False, "error": "下一轮已开启，请勿重复操作"}), 400

    now = _now()
    new_letter = InquiryLetter(
        project_id   = letter.project_id,
        type         = letter.type,
        title        = letter.title,
        content      = letter.content,
        detail       = letter.detail,
        requirements = letter.requirements,
        deadline     = "",
        status       = "待办",
        notes        = letter.notes,
        created_by   = session.get("display_name", ""),
        created_at   = now,
        updated_at   = now,
    )
    db.session.add(new_letter)
    db.session.flush()

    # 复制供应商名单作起点（每轮邀请的供应商不一定相同，可在 7. 询/议价函中增删）
    for s in _suppliers(lid):
        db.session.add(InquirySupplier(
            inquiry_id    = new_letter.id,
            supplier_name = s.supplier_name,
            contact_name  = s.contact_name,
            contact_phone = s.contact_phone,
            email         = s.email,
        ))

    # 复制函件附件（独立副本）
    from models.inquiry_attachment import InquiryAttachment
    atts = db.session.execute(
        db.select(InquiryAttachment).filter_by(inquiry_id=lid).order_by(InquiryAttachment.id)
    ).scalars().all()
    os.makedirs(ATTACH_DIR, exist_ok=True)
    for i, att in enumerate(atts):
        src = os.path.join(PMS_ROOT, att.filepath)
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(att.filename)[1].lower()
        safe_name = f"{new_letter.id}_{int(time.time())}_{i}{ext}"
        shutil.copy2(src, os.path.join(ATTACH_DIR, safe_name))
        db.session.add(InquiryAttachment(
            inquiry_id  = new_letter.id,
            filename    = att.filename,
            filepath    = f"询价附件/上传/{safe_name}",
            uploaded_at = now,
            uploaded_by = session.get("display_name", "") + "（上轮沿用）",
        ))

    # 项目轮次跟进（询议价项目的轮次由函件驱动；邮件主题"第N次"用它）
    proj = db.session.get(Project, letter.project_id)
    new_round = _round_no(letter) + 1
    if proj and (proj.round or 1) < new_round:
        proj.round = new_round
        proj.updated_at = now

    db.session.commit()
    return jsonify({"ok": True,
                    "message": f"已开启第{new_round}轮（待办），请到「7. 询/议价函」中调整供应商并发出邀请",
                    "data": new_letter.to_dict()})


# ─────────────────────────────────────────────────────────────────
# 询价废标后同轮转院内议价（第二轮起）：
# 保留本轮询价废标记录，另建同轮次的议价函/评审，两条过程都可追溯。
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/convert-to-negotiation", methods=["POST"])
@login_required
def convert_to_negotiation(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    review = db.session.execute(
        db.select(InquiryReview).filter_by(inquiry_id=lid)
    ).scalar_one_or_none()
    if not letter:
        return jsonify({"ok": False, "error": "函件不存在"}), 404
    if letter.type != "询价":
        return jsonify({"ok": False, "error": "仅询价函可转为院内议价"}), 400
    if not review or review.status != "已完成" or review.result_type != "废标":
        return jsonify({"ok": False, "error": "仅本轮询价评审完成且废标后才能转为院内议价"}), 400
    cur_round = _round_no(letter)
    if cur_round < 2:
        return jsonify({"ok": False, "error": "询价项目第一轮不允许转为院内议价（第二轮起可转）"}), 400
    newer = db.session.execute(
        db.select(InquiryLetter.id)
        .filter(InquiryLetter.project_id == letter.project_id,
                InquiryLetter.id > letter.id)
    ).first()
    if newer:
        return jsonify({"ok": False, "error": "该项目已开启后续轮次，不能再转议价"}), 400

    now = _now()
    operator = session.get("display_name", "")
    new_letter = InquiryLetter(
        project_id   = letter.project_id,
        type         = "议价",
        title        = (letter.title or "").replace("询价", "议价") or letter.title,
        content      = letter.content,
        detail       = letter.detail,
        requirements = letter.requirements,
        deadline     = _today(),      # 转议价当场评审，不再发函等待
        status       = "进行中",
        notes        = ((letter.notes or "") +
                        f"\n[系统] 第{cur_round}次院内询价废标后转院内议价（{now}），"
                        "沿用询价轮供应商响应资料直接评审").strip(),
        round_no     = cur_round,     # 同轮：仍为第 cur_round 次
        created_by   = operator,
        created_at   = now,
        updated_at   = now,
    )
    db.session.add(new_letter)
    db.session.flush()

    # 供应商：带已递交响应的（议价对象就是他们），响应状态/报价原样沿用，
    # 资格性/符合性结论清空由议价评审重新填写；无响应供应商不带入。
    sups = _suppliers(lid)
    src_sups = [s for s in sups if s.responded] or sups
    sid_map = {}
    for s in src_sups:
        ns = InquirySupplier(
            inquiry_id    = new_letter.id,
            supplier_name = s.supplier_name,
            contact_name  = s.contact_name,
            contact_phone = s.contact_phone,
            email         = s.email,
            sent_at       = now,
            sent_by       = operator + "（询价轮转入）",
            responded     = s.responded,
            quote_amount  = s.quote_amount,
            quote_date    = s.quote_date,
            quote_note    = s.quote_note,
        )
        db.session.add(ns)
        db.session.flush()
        sid_map[s.id] = ns.id

    # 复制供应商响应文件（独立副本，议价评审直接引用）
    resp_files = db.session.execute(
        db.select(InquirySupplierFile).filter_by(inquiry_id=lid)
        .order_by(InquirySupplierFile.id)
    ).scalars().all()
    os.makedirs(RESP_DIR, exist_ok=True)
    for i, rf in enumerate(resp_files):
        if rf.supplier_id not in sid_map:
            continue
        src = os.path.join(PMS_ROOT, rf.filepath)
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(rf.filename)[1].lower()
        safe_name = f"{new_letter.id}_{sid_map[rf.supplier_id]}_{int(time.time())}_{i}{ext}"
        shutil.copy2(src, os.path.join(RESP_DIR, safe_name))
        db.session.add(InquirySupplierFile(
            inquiry_id  = new_letter.id,
            supplier_id = sid_map[rf.supplier_id],
            filename    = rf.filename,
            filepath    = f"询价附件/响应/{safe_name}",
            uploaded_at = now,
            uploaded_by = operator + "（询价轮沿用）",
        ))

    # 复制函件附件（独立副本，与开下一轮同口径）
    from models.inquiry_attachment import InquiryAttachment
    atts = db.session.execute(
        db.select(InquiryAttachment).filter_by(inquiry_id=lid).order_by(InquiryAttachment.id)
    ).scalars().all()
    os.makedirs(ATTACH_DIR, exist_ok=True)
    for i, att in enumerate(atts):
        src = os.path.join(PMS_ROOT, att.filepath)
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(att.filename)[1].lower()
        safe_name = f"{new_letter.id}_{int(time.time())}_{i}{ext}"
        shutil.copy2(src, os.path.join(ATTACH_DIR, safe_name))
        db.session.add(InquiryAttachment(
            inquiry_id  = new_letter.id,
            filename    = att.filename,
            filepath    = f"询价附件/上传/{safe_name}",
            uploaded_at = now,
            uploaded_by = operator + "（询价轮沿用）",
        ))

    # 直接建好议价评审记录（院内议价），转完即可进入 8.1 评审
    new_review = _build_review(new_letter)
    db.session.add(new_review)

    db.session.commit()
    return jsonify({"ok": True,
                    "message": f"已转为第{cur_round}次院内议价，询价废标记录已保留；"
                               f"供应商响应资料已沿用，可直接进行议价评审",
                    "data": new_letter.to_dict()})


# ─────────────────────────────────────────────────────────────────
# 供应商响应文件（邮件附件/邮寄资料，手动上传）
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/suppliers/<int:sid>/files", methods=["GET"])
@login_required
def list_supplier_files(lid, sid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    rows = db.session.execute(
        db.select(InquirySupplierFile).filter_by(inquiry_id=lid, supplier_id=sid)
        .order_by(InquirySupplierFile.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/api/inquiries/<int:lid>/suppliers/<int:sid>/files", methods=["POST"])
@login_required
def upload_supplier_file(lid, sid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    sup = db.session.get(InquirySupplier, sid)
    if not sup or sup.inquiry_id != lid:
        return jsonify({"ok": False, "error": "供应商不存在"}), 404
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ATTACH_ALLOWED:
        return jsonify({"ok": False, "error": f"不支持的文件格式 {ext}，允许：pdf/doc/docx/xls/xlsx/jpg/png/zip/rar"}), 400

    os.makedirs(RESP_DIR, exist_ok=True)
    safe_name = f"{lid}_{sid}_{int(time.time() * 1000)}{ext}"
    f.save(os.path.join(RESP_DIR, safe_name))
    rec = InquirySupplierFile(
        inquiry_id  = lid,
        supplier_id = sid,
        filename    = f.filename,
        filepath    = f"询价附件/响应/{safe_name}",
        uploaded_at = _now(),
        uploaded_by = session.get("display_name", ""),
    )
    db.session.add(rec)
    sup.responded = 1   # 有响应文件即视为已递交响应
    db.session.commit()
    return jsonify({"ok": True, "data": rec.to_dict()}), 201


def _supplier_file(lid, fid):
    rec = db.session.get(InquirySupplierFile, fid)
    if not rec or rec.inquiry_id != lid:
        return None, None
    path = os.path.join(PMS_ROOT, rec.filepath)
    return rec, (path if os.path.exists(path) else None)


@bp.route("/api/inquiries/<int:lid>/supplier-files/<int:fid>", methods=["DELETE"])
@login_required
def delete_supplier_file(lid, fid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    rec, path = _supplier_file(lid, fid)
    if not rec:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    if path:
        try:
            os.remove(path)
        except OSError:
            pass
    db.session.delete(rec)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


@bp.route("/api/inquiries/<int:lid>/supplier-files/<int:fid>/download", methods=["GET"])
@login_required
def download_supplier_file(lid, fid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    rec, path = _supplier_file(lid, fid)
    if not rec:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    if not path:
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    return send_file(path, as_attachment=True, download_name=rec.filename)


@bp.route("/api/inquiries/<int:lid>/supplier-files/<int:fid>/preview", methods=["GET"])
@login_required
def preview_supplier_file(lid, fid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    rec, path = _supplier_file(lid, fid)
    if not rec:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    if not path:
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    from services.office_convert import send_preview
    return send_preview(path, rec.filename)


# ─────────────────────────────────────────────────────────────────
# 拉取邮箱回复 → 标记已响应 + 导入邮件附件为响应文件
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/review/fetch-replies", methods=["POST"])
@login_required
def fetch_replies_into_review(lid):
    """从收件箱抓取本函件的供应商回复：匹配到的供应商置「已响应」，
    回信附件（pdf/word/图片等）自动存为该供应商的响应文件（按文件名去重）。
    匹配规则与 7. 询/议价函的「拉取邮箱回复」一致：
    主题含供应商全称 或 发件地址=供应商邮箱；主题含项目名=确信本项目。"""
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    sups = _suppliers(lid)
    if not sups:
        return jsonify({"ok": False, "error": "该函件没有供应商"}), 400

    from routes.inquiry_api import _norm, _reply_subject_format
    _, proj_name, _ = _reply_subject_format(letter)

    try:
        from services.email_service import fetch_inbox, fetch_attachments_by_uid
        mails = fetch_inbox(limit=300)
    except Exception as e:
        return jsonify({"ok": False, "error": f"收信失败：{e}"}), 502

    np = _norm(proj_name)
    for m in mails:
        m["_ns"] = _norm(m["subject"])
        m["_proj"] = bool(np) and np in m["_ns"]

    # 每家供应商收集匹配邮件：项目名确信的全收（可能多封），否则取最佳一封
    matches = {}     # sid -> [mail, ...]
    matched_idx = set()
    for s in sups:
        nsup = _norm(s.supplier_name)
        nemail = (s.email or "").strip().lower()
        confident, fallback = [], None
        for i, m in enumerate(mails):
            name_hit = bool(nsup) and nsup in m["_ns"]
            mail_hit = bool(nemail) and nemail == (m["from_addr"] or "").lower()
            if not (name_hit or mail_hit):
                continue
            if m["_proj"]:
                confident.append((i, m))
            elif fallback is None:
                fallback = (i, m)
        chosen = confident or ([fallback] if fallback else [])
        if chosen:
            matches[s.id] = [m for _, m in chosen]
            matched_idx.update(i for i, _ in chosen)

    # 下载匹配邮件的附件
    uids = sorted({m["uid"] for ms in matches.values() for m in ms})
    try:
        atts_by_uid = fetch_attachments_by_uid(uids)
    except Exception as e:
        return jsonify({"ok": False, "error": f"下载邮件附件失败：{e}"}), 502

    os.makedirs(RESP_DIR, exist_ok=True)
    now = _now()
    results, imported_total = [], 0
    for s in sups:
        ms = matches.get(s.id)
        if not ms:
            results.append({"supplier_id": s.id, "supplier_name": s.supplier_name,
                            "replied": False, "imported": []})
            continue
        s.responded = 1
        existing = {f.filename for f in db.session.execute(
            db.select(InquirySupplierFile).filter_by(inquiry_id=lid, supplier_id=s.id)
        ).scalars().all()}
        imported = []
        for m in ms:
            for fname, blob in atts_by_uid.get(m["uid"], []):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in ATTACH_ALLOWED or fname in existing:
                    continue
                safe_name = f"{lid}_{s.id}_{int(time.time() * 1000)}_{imported_total}{ext}"
                with open(os.path.join(RESP_DIR, safe_name), "wb") as fh:
                    fh.write(blob)
                db.session.add(InquirySupplierFile(
                    inquiry_id  = lid,
                    supplier_id = s.id,
                    filename    = fname,
                    filepath    = f"询价附件/响应/{safe_name}",
                    uploaded_at = now,
                    uploaded_by = session.get("display_name", "") + "（邮箱抓取）",
                ))
                existing.add(fname)
                imported.append(fname)
                imported_total += 1
        results.append({"supplier_id": s.id, "supplier_name": s.supplier_name,
                        "replied": True, "imported": imported,
                        "reply_subject": ms[0]["subject"], "reply_date": ms[0]["date"]})
    db.session.commit()

    # 主题含项目名但没匹配到任何供应商 → 提示人工归类
    unmatched = [{"subject": m["subject"], "from": m["from_addr"], "date": m["date"]}
                 for i, m in enumerate(mails) if m["_proj"] and i not in matched_idx]

    replied_n = sum(1 for r in results if r["replied"])
    return jsonify({"ok": True,
                    "message": f"匹配到 {replied_n} 家回复，导入附件 {imported_total} 个",
                    "data": {"replied": replied_n, "imported": imported_total,
                             "suppliers": results, "unmatched": unmatched}})


# ─────────────────────────────────────────────────────────────────
# 评定标报告 Excel（项目所有轮次，每轮一个 sheet）
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/review/excel", methods=["GET"])
@login_required
def review_excel(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    review = db.session.execute(
        db.select(InquiryReview).filter_by(inquiry_id=lid)
    ).scalar_one_or_none()
    if not letter or not review:
        return jsonify({"ok": False, "error": "评审记录不存在"}), 404

    from services.inquiry_review_excel import generate_review_excel
    buf = generate_review_excel(letter.project_id, upto_inquiry_id=lid)
    proj = db.session.get(Project, letter.project_id)
    name = (proj.name if proj else "评定标报告").replace("/", "-")
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"评定标报告-{name}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
