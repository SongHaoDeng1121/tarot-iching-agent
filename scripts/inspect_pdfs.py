
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "extracted"

OUT_DIR.mkdir(parents=True, exist_ok=True)

pdf_files = sorted(RAW_DIR.glob("*.pdf"))

if not pdf_files:
    print("没有找到 PDF，请检查 data/raw/ 文件夹。")
    raise SystemExit(1)

for pdf_path in pdf_files:
    print("\n" + "=" * 55)
    print("File:", pdf_path.name)

    with pymupdf.open(pdf_path) as doc:
        print("Total pages:", len(doc))

        # 先只检查前30页，避免一次处理过多资料
        sample_count = min(30, len(doc))
        text_pages = 0

        output_file = OUT_DIR / f"{pdf_path.stem}_sample.txt"

        with output_file.open("w", encoding="utf-8") as f:
            for index in range(sample_count):
                page = doc[index]
                page_text = page.get_text("text", sort=True)

                char_count = len(page_text.strip())

                if char_count >= 100:
                    text_pages += 1

                print(
                    f"PDF Page {index + 1:>3}: "
                    f"{char_count:>5} characters"
                )

                f.write(f"\n--- PDF PAGE {index + 1} ---\n")
                f.write(page_text)
                f.write("\n")

        print("-" * 55)
        print(
            "Pages with >=100 characters:",
            f"{text_pages}/{sample_count}"
        )
        print("Sample saved to:", output_file)
