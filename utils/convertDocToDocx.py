import subprocess
from pathlib import Path


def convert_doc_to_docx(doc_path: str, output_dir: str) -> str:
    try:
        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                output_dir,
                doc_path,
            ],
            check=True,
        )

        converted_file = Path(output_dir) / (Path(doc_path).stem + ".docx")
        if converted_file.exists():
            return str(converted_file)
        else:
            raise FileNotFoundError("Converted .docx file not found.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"LibreOffice conversion failed: {e}")
