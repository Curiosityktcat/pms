from . import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    salt = db.Column(db.String(32), nullable=False)
    pw_hash = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    display_name = db.Column(db.String(50), default="")
    active = db.Column(db.Integer, default=1)
    agency_code = db.Column(db.String(10), default="")

    def to_dict(self):
        return {
            "id": self.id, "username": self.username, "role": self.role,
            "display_name": self.display_name, "active": self.active,
            "agency_code": self.agency_code or "",
        }
