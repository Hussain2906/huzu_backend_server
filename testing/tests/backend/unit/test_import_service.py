import io
import pytest
from fastapi import HTTPException, UploadFile

from app.services.import_service import build_template, parse_csv_upload


@pytest.mark.unit
def test_build_template_unknown_module():
    with pytest.raises(HTTPException):
        build_template("unknown")


@pytest.mark.unit
def test_parse_csv_upload_rejects_non_csv():
    file = UploadFile(filename="data.txt", file=io.BytesIO(b"x"))
    with pytest.raises(HTTPException):
        parse_csv_upload(file)
