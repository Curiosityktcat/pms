from . import db


class AuthLetterRecord(db.Model):
    __tablename__ = "auth_letter_records"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    project_name = db.Column(db.String(200), default="")
    project_number = db.Column(db.String(50), default="")
    round_number = db.Column(db.Integer, default=1)
    bid_time = db.Column(db.String(60), default="")
    supervisor_name = db.Column(db.String(50), default="")
    representative_names = db.Column(db.Text, default="")  # 逗号分隔
    generated_by = db.Column(db.String(50), default="")
    generated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "project_name": self.project_name or "",
            "project_number": self.project_number or "",
            "round_number": self.round_number or 1,
            "bid_time": self.bid_time or "",
            "supervisor_name": self.supervisor_name or "",
            "representative_names": self.representative_names or "",
            "generated_by": self.generated_by or "",
            "generated_at": self.generated_at or "",
        }
