# -*- coding: utf-8 -*-
"""采购需求 Agent 已确认的会话事实。

消息回答了“当时说了什么”，事实表回答“后续计算应以什么为准”。两者分开存，
是为了撤销一项确认时只重算受它影响的步骤，不去篡改历史消息。
"""
import json

from models import db


class DemandAgentFact(db.Model):
    __tablename__ = "demand_agent_facts"
    __table_args__ = (
        db.UniqueConstraint("demand_id", "demand_kind", "key",
                            name="uq_demand_agent_fact_scope_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    demand_id = db.Column(db.Integer, index=True, nullable=False)
    demand_kind = db.Column(db.String(20), default="gov", nullable=False)
    key = db.Column(db.String(160), nullable=False)
    value = db.Column(db.Text, default="")
    source = db.Column(db.String(20), default="model")
    evidence = db.Column(db.Text, default="")
    message_id = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.String(50), default="")
    created_at = db.Column(db.String(30), default="")

    def decoded_value(self):
        try:
            return json.loads(self.value) if self.value else None
        except Exception:                                    # noqa: BLE001
            return self.value

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.decoded_value(),
            "source": self.source or "model",
            "evidence": self.evidence or "",
            "message_id": self.message_id,
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
        }
