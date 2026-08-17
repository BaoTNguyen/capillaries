"""Chunker invariants. No DB, no embedding server."""

from capillaries.chunk import CEILING, FLOOR, TARGET, chunk


def _invariants(text, chunks):
    for c in chunks:
        # Offsets must address the real text — the whole point of storing them.
        assert text[c.char_start:c.char_end] == c.text, c.index
        assert c.text == c.text.strip()
        assert c.text
        if not c.is_atomic:
            assert len(c.text) <= CEILING * 2, f"chunk {c.index} runaway: {len(c.text)}"
    assert [c.index for c in chunks] == list(range(len(chunks)))
    # Document order, no overlap.
    for a, b in zip(chunks, chunks[1:]):
        assert a.char_end <= b.char_start


def test_short_prompt_is_one_chunk():
    text = "Write a product requirements document for [FEATURE]."
    cs = chunk(text)
    assert len(cs) == 1
    assert cs[0].text == text
    _invariants(text, cs)


def test_empty():
    assert chunk("") == []
    assert chunk("   \n\n  ") == []


def test_xml_sections_split_and_label():
    role = "You are a strategist who thinks in systems. " * 40      # ~1.7k
    rules = "Never invent a figure the user did not provide. " * 40
    text = f"<role>\n{role}\n</role>\n\n<guardrails>\n{rules}\n</guardrails>\n"
    cs = chunk(text)
    assert len(cs) >= 2
    assert {c.label for c in cs} & {"role", "guardrails"}
    _invariants(text, cs)


def test_headings_split_when_no_xml():
    body = "Some prose that goes on for a while. " * 45
    text = "".join(f"## Section {i}\n\n{body}\n\n" for i in range(4))
    cs = chunk(text)
    assert len(cs) >= 2
    assert any(c.label and c.label.startswith("Section") for c in cs)
    _invariants(text, cs)


def test_unstructured_falls_back_to_paragraphs():
    # 510 of 916 vault prompts have no XML tag, heading, rule or bold header.
    text = "\n\n".join(
        f"Paragraph {i} of plain prose with no structural markers whatsoever. " * 20
        for i in range(8)
    )
    cs = chunk(text)
    assert len(cs) >= 2
    _invariants(text, cs)


def test_code_fence_is_never_split():
    fence = "```python\n" + "\n".join(f"# line {i} --- not a rule" for i in range(120)) + "\n```"
    text = f"<role>\nIntro paragraph.\n</role>\n\n{fence}\n"
    cs = chunk(text)
    joined = [c for c in cs if "```python" in c.text]
    assert len(joined) == 1, "fence appeared in more than one chunk"
    assert joined[0].text.count("```") == 2, "fence was cut in half"
    _invariants(text, cs)


def test_table_rows_stay_together():
    table = "\n".join(["| a | b |", "|---|---|"] + [f"| {i} | x |" for i in range(80)])
    text = f"## Data\n\nLead-in.\n\n{table}\n"
    cs = chunk(text)
    holding = [c for c in cs if "| 0 | x |" in c.text]
    assert len(holding) == 1
    assert "| 79 | x |" in holding[0].text
    _invariants(text, cs)


def test_self_duplicate_collapses():
    # 169 prompts in the vault repeat their own opening verbatim after a rule.
    half = "<role>\nYou are a strategist.\n</role>\n\n" + ("Body text here. " * 120)
    text = half + "\n\n---\n\n" + half
    cs = chunk(text)
    bodies = [" ".join(c.text.split()) for c in cs]
    assert len(bodies) == len(set(bodies)), "duplicate chunk survived"
    _invariants(text, cs)


def test_no_tiny_trailing_chunk():
    body = "Sentence number one goes here. " * 70
    text = f"## A\n\n{body}\n\n## B\n\nok\n"
    cs = chunk(text)
    if len(cs) > 1:
        assert len(cs[-1].text) >= FLOOR or cs[-1].is_atomic
    _invariants(text, cs)


def test_giant_prompt_stays_bounded():
    # The vault's largest prompt is 41 881 chars.
    text = "\n\n".join(f"**Header {i}**\n\n" + "Filler sentence. " * 40 for i in range(120))
    cs = chunk(text)
    assert len(cs) > 5
    assert max(len(c.text) for c in cs) <= CEILING * 2
    assert sum(len(c.text) for c in cs) > len(text) * 0.9, "content was dropped"
    _invariants(text, cs)


def test_packing_reaches_target():
    body = "\n\n".join(f"Short para {i}. " * 5 for i in range(60))
    cs = chunk(body)
    # Small paragraphs must be packed up, not emitted one per chunk.
    assert all(len(c.text) >= TARGET * 0.5 for c in cs[:-1])
    _invariants(body, cs)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all chunker invariants hold")
