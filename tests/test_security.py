import pytest
from factlens.security import (
    validate_pdf_bytes,
    sanitize_filename,
    sanitize_untrusted_text,
    compute_sha256
)

def test_validate_pdf_bytes_valid():
    valid_pdf_sample = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    is_valid, err = validate_pdf_bytes(valid_pdf_sample)
    assert is_valid is True
    assert err is None

def test_validate_pdf_bytes_invalid_header():
    fake_file = b"This is not a PDF file at all."
    is_valid, err = validate_pdf_bytes(fake_file)
    assert is_valid is False
    assert "magic header" in err

def test_validate_pdf_bytes_too_small():
    is_valid, err = validate_pdf_bytes(b"%PDF")
    assert is_valid is False
    assert "too small" in err

def test_sanitize_filename_traversal():
    bad_name = "../../../etc/passwd"
    clean = sanitize_filename(bad_name)
    assert "/" not in clean
    assert ".." not in clean
    assert clean.endswith(".pdf")

def test_sanitize_filename_special_chars():
    bad_name = "my document <script>alert(1)</script>.pdf"
    clean = sanitize_filename(bad_name)
    assert "<" not in clean
    assert ">" not in clean
    assert clean.endswith(".pdf")

def test_sanitize_untrusted_text():
    raw_html = "<script>alert('xss')</script> Delhivery FY24 revenue"
    sanitized = sanitize_untrusted_text(raw_html)
    assert "<script>" not in sanitized
    assert "&lt;script&gt;" in sanitized

def test_compute_sha256():
    data = b"%PDF-1.4 sample content"
    digest = compute_sha256(data)
    assert len(digest) == 64
    assert isinstance(digest, str)
