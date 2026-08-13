"""归档「文件夹视图」的真实附件枚举。

把一个项目在各业务模块下上传/生成的**文件资料**统一收集成若干文件夹，
每个文件项直接给出复用各模块已有下载/预览端点的 URL（这些端点均已做
can_view_project 归属鉴权），避免在归档侧重复实现文件服务。

覆盖：
  - 采购需求资料 / 采购文件 / 项目评审资料 / 采购结果单价报价 / 中标通知书
    （同存 ProcurementDocAttachment 表，按 kind 区分，统一走归档通用附件端点
     /api/archive/<pid>/attachment/<aid>）
  - 采购合同（上传合同文件 + 合同附件）
  - 采购公告（生成 word + 上传附件）
  - 询价/议价函（生成 word + 上传附件）
"""
from models import db
from models.procurement_doc_attachment import ProcurementDocAttachment
from models.contract import Contract
from models.contract_attachment import ContractAttachment
from models.announcement import Announcement
from models.announcement_attachment import AnnouncementAttachment
from models.inquiry_letter import InquiryLetter
from models.inquiry_attachment import InquiryAttachment

# ProcurementDocAttachment 各 kind → 归档文件夹名（顺序即展示顺序）
_DOC_KIND_FOLDER = [
    ("demand",        "采购需求资料"),
    ("doc",           "采购文件"),
    ("review_result", "项目评审资料"),
    ("result",        "采购结果·单价/报价单"),
    ("award_notice",  "中标通知书"),
]


def _cn_round(n):
    try:
        n = int(n or 1)
    except (TypeError, ValueError):
        n = 1
    return f"第{'一二三四五六七八九十'[n - 1]}次" if 1 <= n <= 10 else f"第{n}次"


def collect_material_folders(project):
    """返回 [{folder, items:[{name,url,preview_url,size}]}]（仅含有文件的文件夹）。"""
    pid = project.id
    folders = []

    # ① ProcurementDocAttachment 家族 —— 统一走归档通用附件端点
    for kind, folder in _DOC_KIND_FOLDER:
        atts = db.session.execute(
            db.select(ProcurementDocAttachment)
            .filter_by(project_id=pid, kind=kind)
            .order_by(ProcurementDocAttachment.round_number, ProcurementDocAttachment.id)
        ).scalars().all()
        items = []
        for a in atts:
            items.append({
                "name": f"{_cn_round(a.round_number)}｜{a.original_name or a.saved_name}",
                "size": a.file_size or 0,
                "url": f"/api/archive/{pid}/attachment/{a.id}?download=1",
                "preview_url": f"/api/archive/{pid}/attachment/{a.id}",
            })
        if items:
            folders.append({"folder": folder, "items": items})

    # ② 采购合同（上传合同文件 + 合同附件）
    contracts = db.session.execute(
        db.select(Contract).filter_by(project_id=pid).order_by(Contract.id)
    ).scalars().all()
    citems = []
    for c in contracts:
        tag = f"包{c.package_no}｜" if c.package_no else ""
        if c.file_saved_name:
            citems.append({
                "name": f"{tag}{c.file_name or '合同文件'}",
                "size": 0,
                "url": f"/api/contracts/{c.id}/file",
                "preview_url": f"/api/contracts/{c.id}/file/preview",
            })
        atts = db.session.execute(
            db.select(ContractAttachment).filter_by(contract_id=c.id)
            .order_by(ContractAttachment.id)
        ).scalars().all()
        for a in atts:
            citems.append({
                "name": f"{tag}{a.original_name}",
                "size": a.file_size or 0,
                "url": f"/api/contracts/{c.id}/attachments/{a.id}/download",
                "preview_url": f"/api/contracts/{c.id}/attachments/{a.id}/preview",
            })
    if citems:
        folders.append({"folder": "采购合同", "items": citems})

    # ③ 采购公告（生成 word + 上传附件）
    anns = db.session.execute(
        db.select(Announcement).filter_by(project_id=pid).order_by(Announcement.id)
    ).scalars().all()
    aitems = []
    for ann in anns:
        rp = _cn_round(getattr(ann, "round_number", 1))
        aitems.append({
            "name": f"{rp}｜采购公告.docx",
            "size": 0,
            "url": f"/api/announcements/{ann.id}/word",
            "preview_url": f"/api/announcements/{ann.id}/word",
        })
        files = db.session.execute(
            db.select(AnnouncementAttachment).filter_by(announcement_id=ann.id)
            .order_by(AnnouncementAttachment.id)
        ).scalars().all()
        for fa in files:
            aitems.append({
                "name": f"{rp}｜{fa.original_name}",
                "size": fa.file_size or 0,
                "url": f"/api/announcements/{ann.id}/files/{fa.id}",
                "preview_url": f"/api/announcements/{ann.id}/files/{fa.id}/preview",
            })
    if aitems:
        folders.append({"folder": "采购公告", "items": aitems})

    # ④ 询价/议价函（生成 word + 上传附件）
    letters = db.session.execute(
        db.select(InquiryLetter).filter_by(project_id=pid).order_by(InquiryLetter.id)
    ).scalars().all()
    iitems = []
    for L in letters:
        label = f"{L.type}函"
        iitems.append({
            "name": f"{label}·{L.title or ('#' + str(L.id))}.docx",
            "size": 0,
            "url": f"/api/inquiries/{L.id}/word",
            "preview_url": f"/api/inquiries/{L.id}/word/preview",
        })
        atts = db.session.execute(
            db.select(InquiryAttachment).filter_by(inquiry_id=L.id)
            .order_by(InquiryAttachment.id)
        ).scalars().all()
        for a in atts:
            iitems.append({
                "name": f"{label}｜{a.filename}",
                "size": 0,
                "url": f"/api/inquiries/{L.id}/attachments/{a.id}/download",
                "preview_url": f"/api/inquiries/{L.id}/attachments/{a.id}/preview",
            })
    if iitems:
        folders.append({"folder": "询价/议价函", "items": iitems})

    # ⑤ 审批过程记录（驳回/不确认的完整往返，系统按留痕生成）
    from models.approval_log import ApprovalLog
    n_log = db.session.execute(
        db.select(db.func.count(ApprovalLog.id)).where(ApprovalLog.project_id == pid)
    ).scalar() or 0
    n_reject = db.session.execute(
        db.select(db.func.count(ApprovalLog.id)).where(
            ApprovalLog.project_id == pid,
            ApprovalLog.action.in_(("reject", "not_confirm")),
        )
    ).scalar() or 0
    folders.append({"folder": "审批过程记录", "items": [{
        "name": f"审批过程记录表.docx（共{n_log}次往返，其中驳回/不确认{n_reject}次）",
        "size": 0,
        "url": f"/api/archive/{pid}/approval-record",
        "preview_url": f"/api/archive/{pid}/approval-record",
    }]})

    return folders
