"""PDF 文本提取；仅在页面没有可复制文本时调用本机 OCR。"""

from __future__ import annotations

import pymupdf

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PAGES = 50


class PDFTextError(ValueError):
    """用户可直接处理的 PDF 输入错误。"""


def _ocr_page(page: pymupdf.Page) -> str:
    """识别扫描页，依赖本机 Tesseract 与 chi_sim/eng 语言包。"""

    try:
        text_page = page.get_textpage_ocr(language="chi_sim+eng", dpi=200)
        return page.get_text(textpage=text_page).strip()
    except Exception as exc:
        raise PDFTextError(
            "扫描件 OCR 不可用：请安装 Tesseract 及 chi_sim、eng 语言包，或粘贴病历文本"
        ) from exc


def _needs_ocr(page: pymupdf.Page, extracted: str) -> bool:
    """空白页或含大面积扫描图像的页面使用 OCR，避免文字页眉掩盖正文。"""

    if not extracted:
        return True
    page_area = page.rect.get_area()
    if not page_area:
        return False
    image_area = sum(
        pymupdf.Rect(image["bbox"]).get_area() for image in page.get_image_info()
    )
    return image_area >= page_area * 0.25


def extract_pdf_text(data: bytes) -> str:
    """从数字 PDF/扫描 PDF 提取文字。

    完整伪代码：
        校验上传对象为非空 PDF 且不超过 10 MB
        打开 PDF 并校验页数不超过 50
        逐页提取可复制文字；空白页或含大面积扫描图像的页面调用本机 OCR
        按页连接非空文本；若全部为空则报告错误
        关闭 PDF 并返回可编辑的文本
    """

    if not isinstance(data, bytes) or not data.startswith(b"%PDF"):
        raise PDFTextError("请上传有效的 PDF 文件")
    if len(data) > MAX_PDF_BYTES:
        raise PDFTextError("PDF 文件不能超过 10 MB")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.page_count > MAX_PAGES:
                raise PDFTextError("PDF 不能超过 50 页")
            pages = []
            for page in document:
                extracted = page.get_text().strip()
                if _needs_ocr(page, extracted):
                    recognized = _ocr_page(page)
                    if not recognized:
                        raise PDFTextError("扫描页 OCR 未提取到文字，请检查文件或粘贴病历文本")
                    pages.append(
                        recognized if not extracted or extracted in recognized
                        else extracted + "\n" + recognized
                    )
                else:
                    pages.append(extracted)
    except PDFTextError:
        raise
    except Exception as exc:
        raise PDFTextError("PDF 无法读取或文件已损坏") from exc
    text = "\n\n".join(part for part in pages if part).strip()
    if not text:
        raise PDFTextError("未提取到病历文字，请检查 PDF 或直接粘贴文本")
    return text
