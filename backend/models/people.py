from . import db


class People(db.Model):
    __tablename__ = "people"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    id_card = db.Column(db.String(20), default="")
    photo = db.Column(db.String(200), default="")
    role_type = db.Column(db.String(20), default="supervisor")
    active = db.Column(db.Integer, default=1)
    department = db.Column(db.String(100), default="")
    position = db.Column(db.String(200), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "id_card": self.id_card,
            "photo": self.photo,
            "role_type": self.role_type,
            "active": self.active,
            "department": self.department or "",
            "position": self.position or "",
        }
