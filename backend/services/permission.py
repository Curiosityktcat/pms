"""菜单权限目录与角色权限读写。

权限粒度 = 菜单节点（perm_key 与前端菜单 key 一致）。
admin 角色拥有全部权限，不入 role_permissions 表。
开发中（disabled）的菜单不纳入权限控制。
"""
from models import db
from models.role_permission import RolePermission

ADMIN_ROLE = "admin"
# 系统管理员账号（用户名）：拥有全部权限，且是唯一可配置权限矩阵的账号。
# 注意其角色仍是 assistant，超级权限按用户名识别。
ADMIN_USERNAME = "admin"

# 权限目录：分组 → 菜单项。前端据此渲染权限矩阵，顺序即展示顺序。
PERMISSION_CATALOG = [
    {
        "group": "采购需求编制",
        "items": [
            {"key": "procurement-demand-gov", "label": "1.1 政府采购需求"},
            {"key": "internal-bid-demand", "label": "1.2 院内竞选需求编制"},
            {"key": "procurement-demand-sole", "label": "1.3 单一来源需求"},
            {"key": "procurement-demand-inquiry", "label": "1.4 询议价需求"},
            {"key": "procurement-demand-emergency", "label": "1.5 紧急采购登记"},
        ],
    },
    {
        "group": "项目分发",
        "items": [
            {"key": "dispatch", "label": "2. 采购项目分发"},
        ],
    },
    {
        "group": "代理协议",
        "items": [
            {"key": "agency-agreement", "label": "3. 代理协议"},
        ],
    },
    {
        "group": "采购部项目管理",
        "items": [
            {"key": "new", "label": "4.1 项目立项"},
            {"key": "flow", "label": "4.2 项目流程"},
            {"key": "bid", "label": "开标管理"},
            {"key": "bid-board", "label": "开标看板"},
            {"key": "auth-letter", "label": "授权函"},
        ],
    },
    {
        "group": "采购文件编制",
        "items": [
            {"key": "doc", "label": "5. 采购文件编制"},
        ],
    },
    {
        "group": "挂网管理",
        "items": [
            {"key": "announcement", "label": "6.1 采购公告"},
        ],
    },
    {
        "group": "其他业务",
        "items": [
            {"key": "inquiry", "label": "7. 询/议价函"},
            {"key": "inquiry-review", "label": "8.1 询议价评审"},
            {"key": "project-review", "label": "8.5 项目评审资料上传"},
            {"key": "procurement-result", "label": "9. 采购结果确认"},
            {"key": "contract", "label": "10. 合同管理"},
        ],
    },
    {
        "group": "归档",
        "items": [
            {"key": "archive", "label": "11. 归档"},
        ],
    },
    {
        "group": "文件识别",
        "items": [
            {"key": "file-ocr", "label": "12. 文件识别"},
        ],
    },
    {
        "group": "投标文件审查",
        "items": [
            {"key": "bid-review", "label": "投标文件审查（AI 辅助）"},
        ],
    },
    {
        "group": "基础数据维护",
        "items": [
            {"key": "people-manage", "label": "13.1 人员维护"},
            {"key": "template-manage", "label": "13.2 模板维护"},
            {"key": "email-settings", "label": "13.3 邮件设置"},
            {"key": "scraper-settings", "label": "13.4 抓取模型设置"},
        ],
    },
]

ALL_PERM_KEYS = [item["key"] for grp in PERMISSION_CATALOG for item in grp["items"]]
_ALL_PERM_SET = set(ALL_PERM_KEYS)

# 各业务角色的默认权限（仅在 role_permissions 表为空时一次性写入）
DEFAULT_ROLE_PERMS = {
    # 采购部助理：分发与日常业务，立项除外
    "assistant": [
        "procurement-demand-gov", "internal-bid-demand", "procurement-demand-sole",
        "procurement-demand-inquiry", "procurement-demand-emergency", "dispatch",
        "agency-agreement", "doc",
        "flow", "bid", "bid-board", "auth-letter", "announcement",
        "inquiry", "inquiry-review", "project-review", "procurement-result", "contract", "archive",
        "file-ocr", "bid-review",
        "people-manage", "template-manage", "email-settings", "scraper-settings",
    ],
    # 采购部助理（受限/分发岗，如陈梦霞）：仅 项目分发 / 归档 / 项目流程(查看进度)，后续按需加
    "pd_assistant": ["dispatch", "archive", "flow"],
    # 项目经办人：立项及项目执行
    "officer": [
        "procurement-demand-gov", "internal-bid-demand", "procurement-demand-sole",
        "procurement-demand-inquiry", "procurement-demand-emergency",
        "agency-agreement", "doc",
        "new", "flow", "bid", "bid-board", "auth-letter", "announcement",
        "inquiry", "inquiry-review", "project-review", "procurement-result", "contract",
        "file-ocr", "bid-review",
    ],
    # 采购部负责人：全部业务权限
    "leader": list(ALL_PERM_KEYS),
    # 代理机构：协办相关。可见 4(项目流程/开标管理/开标看板/授权函)、5采购文件编制、
    # 6采购公告、9采购结果、10合同；发布/确认类动作由经办人完成（见各 API 角色校验）。
    "agency": [
        "flow", "bid", "bid-board", "auth-letter",
        "doc", "announcement", "project-review", "procurement-result", "contract",
    ],
    # 监督：开标相关
    "supervisor": ["flow", "bid", "bid-board"],
}


def is_admin_user(username):
    """是否为系统管理员账号。"""
    return username == ADMIN_USERNAME


def get_user_perms(username, role):
    """返回某用户实际拥有的权限 key 列表。

    管理员账号无视角色直接拥有全部权限；其余按角色权限表。
    """
    if is_admin_user(username):
        return list(ALL_PERM_KEYS)
    return get_role_perms(role)


def get_role_perms(role):
    """返回某角色的权限 key 列表。admin 拥有全部。"""
    if role == ADMIN_ROLE:
        return list(ALL_PERM_KEYS)
    rows = db.session.execute(
        db.select(RolePermission.perm_key).filter_by(role=role)
    ).scalars().all()
    # 仅保留仍在目录中的 key，过滤历史遗留
    return [k for k in rows if k in _ALL_PERM_SET]


def set_role_perms(role, keys):
    """覆盖式设置某角色的权限。admin 不可改（始终全部）。"""
    if role == ADMIN_ROLE:
        return
    valid = [k for k in keys if k in _ALL_PERM_SET]
    db.session.execute(
        db.delete(RolePermission).filter_by(role=role)
    )
    for k in valid:
        db.session.add(RolePermission(role=role, perm_key=k))
    db.session.commit()


def seed_default_perms():
    """首次（表为空）写入各角色默认权限。"""
    count = db.session.execute(
        db.select(db.func.count()).select_from(RolePermission)
    ).scalar_one()
    if count:
        return
    for role, keys in DEFAULT_ROLE_PERMS.items():
        for k in keys:
            db.session.add(RolePermission(role=role, perm_key=k))
    db.session.commit()
