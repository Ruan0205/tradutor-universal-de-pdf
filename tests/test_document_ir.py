import unittest

from engine.document_ir import (
    BBox,
    DOCUMENT_IR_VERSION,
    IRBlock,
    IRDocument,
    IRPage,
    IRTextLine,
    Provenance,
    TextStyle,
    stable_id,
)


class DocumentIRTests(unittest.TestCase):
    def test_round_trip_preserves_core_fields(self):
        doc = IRDocument(
            document_id="doc-1",
            source_path="fixtures/simple.pdf",
            checksum="abc123",
            source_language="en",
            pages=[
                IRPage(
                    page_id="page-1",
                    page_number=1,
                    width=612,
                    height=792,
                    classification=["digital"],
                    blocks=[
                        IRBlock(
                            block_id="page-1-block-1",
                            type="paragraph",
                            bbox=BBox(10, 20, 200, 60),
                            original_text="Example text",
                            translated_text="Texto de exemplo",
                            status="validated",
                            translation_provider="mock",
                            translation_model="mock-model",
                            lines=[
                                IRTextLine(
                                    line_id="page-1-line-1",
                                    bbox=BBox(10, 20, 200, 35),
                                    original_text="Example text",
                                    translated_text="Texto de exemplo",
                                    style=TextStyle(font_name="Times", font_size=12, font_category="serif"),
                                    provenance=[
                                        Provenance(
                                            source="digital_text",
                                            tool="pymupdf",
                                            tool_version="unknown",
                                            confidence=1.0,
                                        )
                                    ],
                                )
                            ],
                        )
                    ],
                )
            ],
        )

        restored = IRDocument.from_json(doc.to_json())

        self.assertEqual(restored.ir_version, DOCUMENT_IR_VERSION)
        self.assertEqual(restored.document_id, "doc-1")
        self.assertEqual(restored.pages[0].classification, ["digital"])
        self.assertEqual(restored.pages[0].blocks[0].translated_text, "Texto de exemplo")
        self.assertEqual(restored.pages[0].blocks[0].lines[0].style.font_category, "serif")

    def test_stable_id_normalizes_human_readable_parts(self):
        self.assertEqual(stable_id("Page 12", "Block", 8), "page-12-block-8")

    def test_rejects_unknown_ir_version(self):
        data = {
            "ir_version": "999.0.0",
            "document_id": "doc-1",
            "source_path": "x.pdf",
            "checksum": "abc",
            "pages": [],
        }

        with self.assertRaises(ValueError):
            IRDocument.from_dict(data)


if __name__ == "__main__":
    unittest.main()
