from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def create_dataset(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    outputs = []

    simple = root / "digital-simple.pdf"
    c = canvas.Canvas(str(simple), pagesize=letter)
    c.setFont("Times-Roman", 12)
    c.drawString(72, 720, "The wizard casts a spell at the beginning of the round.")
    c.drawString(72, 700, "A successful saving throw reduces the damage by half.")
    c.save()
    outputs.append(simple)

    columns = root / "two-columns-table.pdf"
    c = canvas.Canvas(str(columns), pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 735, "Sample Encounter")
    c.setFont("Helvetica", 10)
    left = ["Creatures act in initiative order.", "Difficult terrain costs extra movement."]
    right = ["Table 1: Damage", "Level 1  1d6", "Level 2  2d6"]
    for idx, line in enumerate(left):
        c.drawString(72, 700 - idx * 16, line)
    for idx, line in enumerate(right):
        c.drawString(330, 700 - idx * 16, line)
    c.rect(330, 650, 160, 48)
    c.line(330, 674, 490, 674)
    c.line(410, 650, 410, 698)
    c.save()
    outputs.append(columns)

    return outputs


if __name__ == "__main__":
    for path in create_dataset(Path("tests/fixtures/generated")):
        print(path)
