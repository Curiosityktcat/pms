from . import db


class Agency(db.Model):
    __tablename__ = "agencies"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name, "active": self.active}
