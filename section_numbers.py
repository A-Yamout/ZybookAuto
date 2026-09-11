from __future__ import annotations


def section_number(section: dict, chapter_number: int | None = None) -> int:
    """Return the integer section index within a chapter.

    ZyBooks can expose both `number` (for example 10) and
    `canonical_section_number` (for example "1.10"). The per-chapter `number`
    is preferred because treating canonical identifiers as numeric decimals
    breaks sections 1.10, 1.11, and above.
    """
    raw_number = section.get("number")
    if raw_number is not None:
        try:
            return int(raw_number)
        except (TypeError, ValueError):
            pass

    canonical = section.get("canonical_section_number")
    if canonical is None:
        raise ValueError("Section has no usable number")

    text = str(canonical).strip()
    if "." in text:
        chapter_text, section_text = text.split(".", 1)
        if chapter_number is None or chapter_text == str(chapter_number):
            return int(section_text)
        return int(section_text)

    return int(text)
