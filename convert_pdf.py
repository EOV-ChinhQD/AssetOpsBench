import pymupdf4llm
import pathlib

# Using try-except to handle potential errors during conversion
try:
    md_text = pymupdf4llm.to_markdown("Giai-phau-agentic-os.pdf")
    pathlib.Path("Giai-phau-agentic-os.md").write_bytes(md_text.encode('utf-8'))
    print("PDF converted successfully to Giai-phau-agentic-os.md")
except Exception as e:
    print(f"Error during conversion: {e}")
