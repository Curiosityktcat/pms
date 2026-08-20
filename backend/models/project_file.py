# -*- coding: utf-8 -*-
"""项目管理器里补传的项目资料。

各业务模块（采购需求、采购文件、评审、结果、合同…）都有自己的附件表，
归档树会把它们汇总起来。这张表只放**在项目管理器里额外补传**的材料，
和业务附件分开存，删这里的东西不会误伤业务流程上的文件。
"""
from models import db


class ProjectFile(db.Model):
    __tablename__ = "project_files"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"),
                           index=True, nullable=False)
    original_name = db.Column(db.String(300), default="")   # 上传时的原名，界面显示这个
    saved_name = db.Column(db.String(200), default="")      # 存盘名，带随机串防同名覆盖
    folder = db.Column(db.String(200), default="")          # 项目文件夹内的相对子目录
    size = db.Column(db.Integer, default=0)
    uploaded_by = db.Column(db.String(50), default="")
    uploaded_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
