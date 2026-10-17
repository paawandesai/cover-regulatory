from app.search import search as S


class FakeConn:
    def execute(self, *_):
        heads = [
            "SEC. 12.08. “R1” ONE-FAMILY ZONE.",
            "SEC. 12.08.5. “RW1” RESIDENTIAL WATERWAYS ZONE.",
            "SEC. 12.07.01. “RE” RESIDENTIAL ESTATE ZONE.",
            "SEC. 12.09. “R2” TWO-FAMILY ZONE.",
            "SEC. 12.22. EXCEPTIONS.",
        ]
        return type("R", (), {"fetchall": lambda self: [{"heading": h} for h in heads]})()


def test_named_zones_map_to_their_own_sections(monkeypatch):
    monkeypatch.setattr(S, "_zone_sections", None)
    c = FakeConn()
    assert S.named_zone_sections("What side yard is required in the R1 zone?", c) == ["LAMC 12.08"]
    assert S.named_zone_sections("RE15 front yard", c) == ["LAMC 12.07.01"]
    assert S.named_zone_sections("R1-1 or R2-1 lots", c) == ["LAMC 12.08", "LAMC 12.09"]
    assert S.named_zone_sections("Is a JADU allowed? EXCEPTIONS", c) == []
    monkeypatch.setattr(S, "_zone_sections", None)
