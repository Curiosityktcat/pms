from models import db


class DocForm(db.Model):
    """文档式表单数据：一个项目 + 一个模板(采购需求/采购文件) = 一条记录。

    学四川政采「数据驱动文档式填空编辑器」：字段数据结构化存 JSON（data），
    模板(章节/字段定义)在 services/doc_templates.py 配置，前端渲染成文档样式编辑，
    导出时按模板生成 Word。便于后续随时改模板字段而不动数据结构。
    """
    __tablename__ = "doc_forms"
    __table_args__ = (db.UniqueConstraint("project_id", "template_key",
                                          name="uq_docform_project_template"),)

    id           = db.Column(db.Integer, primary_key=True)
    project_id   = db.Column(db.Integer, index=True, nullable=False)
    template_key = db.Column(db.String(40), index=True, nullable=False)  # procurement_demand | procurement_doc
    data         = db.Column(db.Text, default="{}")    # 字段值 JSON 字符串
    status       = db.Column(db.String(10), default="草稿")  # 草稿 | 已完成
    updated_by   = db.Column(db.String(50), default="")
    updated_at   = db.Column(db.String(30), default="")
    created_at   = db.Column(db.String(30), default="")

    def to_dict(self):
        import json
        try:
            data = json.loads(self.data or "{}")
        except Exception:
            data = {}
        return {
            "id": self.id,
            "project_id": self.project_id,
            "template_key": self.template_key,
            "data": data,
            "status": self.status or "草稿",
            "updated_by": self.updated_by or "",
            "updated_at": self.updated_at or "",
        }
