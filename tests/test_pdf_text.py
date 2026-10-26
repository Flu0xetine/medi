"""PDF 文本提取的输入边界与 OCR 回退测试。"""

import unittest
import base64
from unittest.mock import patch

import pymupdf

from medi.web.pdf_text import PDFTextError, _ocr_page, extract_pdf_text


class PDFTextTests(unittest.TestCase):
    def test_digital_pdf(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "Medical record 123")
        self.assertIn("Medical record 123", extract_pdf_text(document.tobytes()))

    def test_scanned_page_uses_ocr(self) -> None:
        document = pymupdf.open()
        document.new_page()
        with patch("medi.web.pdf_text._ocr_page", return_value="识别出的病历") as ocr:
            self.assertEqual(extract_pdf_text(document.tobytes()), "识别出的病历")
        ocr.assert_called_once()

    def test_large_scanned_body_with_selectable_header_uses_ocr(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 40), "Page 1")
        pixel = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p0cAAAAASUVORK5CYII="
        )
        page.insert_image(pymupdf.Rect(30, 80, 560, 700), stream=pixel)
        with patch("medi.web.pdf_text._ocr_page", return_value="Page 1 患者胸痛") as ocr:
            self.assertIn("患者胸痛", extract_pdf_text(document.tobytes()))
        ocr.assert_called_once()

    def test_large_scanned_body_with_long_selectable_header_uses_ocr(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((30, 40), "Header " * 13)
        pixel = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p0cAAAAASUVORK5CYII="
        )
        page.insert_image(pymupdf.Rect(30, 80, 560, 700), stream=pixel)
        with patch("medi.web.pdf_text._ocr_page", return_value="患者呼吸困难") as ocr:
            self.assertIn("患者呼吸困难", extract_pdf_text(document.tobytes()))
        ocr.assert_called_once()

    def test_invalid_and_empty_pdf(self) -> None:
        with self.assertRaises(PDFTextError):
            extract_pdf_text(b"not a pdf")
        document = pymupdf.open()
        document.new_page()
        with patch("medi.web.pdf_text._ocr_page", return_value=""):
            with self.assertRaisesRegex(PDFTextError, "未提取到"):
                extract_pdf_text(document.tobytes())

    def test_rejects_large_pdf(self) -> None:
        with self.assertRaisesRegex(PDFTextError, "10 MB"):
            extract_pdf_text(b"%PDF" + b"x" * (10 * 1024 * 1024))

    def test_rejects_more_than_fifty_pages(self) -> None:
        document = pymupdf.open()
        for _ in range(51):
            document.new_page()
        with self.assertRaisesRegex(PDFTextError, "50 页"):
            extract_pdf_text(document.tobytes())

    def test_missing_ocr_runtime_reports_actionable_error(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        with patch.object(page, "get_textpage_ocr", side_effect=RuntimeError("missing data")):
            with self.assertRaisesRegex(PDFTextError, "Tesseract"):
                _ocr_page(page)


if __name__ == "__main__":
    unittest.main()
