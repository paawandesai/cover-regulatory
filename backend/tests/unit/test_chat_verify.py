from app.api.chat import Answer, Quote, Sentence, verify

CHUNKS = [
    {
        "id": "c1",
        "text": "The front yard shall be not less than 20 feet in depth.",
        "section_id": "12.08 C.1",
        "source_url": "",
        "page_start": None,
    }
]
ITEMS = [{"id": "height", "family": "envelope", "title": "Height", "value": 33, "unit": "ft", "citations": []}]


def _one(text, quotes=(), items=()):
    return verify(Answer(sentences=[Sentence(text=text, quotes=list(quotes), items=list(items))]), CHUNKS, ITEMS)


def test_numbers_from_the_quote_or_section_are_kept():
    q = Quote(chunk_id="c1", quote="not less than 20 feet in depth")
    assert _one("Section 12.08 C.1 requires a front yard of 20 feet.", [q])


def test_a_number_not_in_the_quote_is_dropped():
    q = Quote(chunk_id="c1", quote="not less than 20 feet in depth")
    assert _one("The front yard can be 5 feet with a variance.", [q]) == []


def test_a_restated_value_keeps_its_own_number_only():
    assert _one("The height limit is 33 ft.", items=["height"])
    assert _one("The height limit is 45 ft.", items=["height"]) == []
