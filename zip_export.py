# zip_export.py
from io import BytesIO
import zipfile
import pdf_export
from export_utils import safe_filename


def build_bulk_zip(people_records):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in people_records:
            person = entry["person"]
            records = entry["records"]
            pdf_buf = pdf_export.build_patient_pdf(person["name"], person["id"], records)
            filename = f"{safe_filename(person['name'])}_BP-{person['id']}.pdf"
            zf.writestr(filename, pdf_buf.getvalue())
    zip_buffer.seek(0)
    return zip_buffer
