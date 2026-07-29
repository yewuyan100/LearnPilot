from pathlib import Path
from typing import Protocol

from app.services.material_processing.types import ParsedDocument


class MaterialParser(Protocol):
    parser_type: str

    def parse(self, path: Path) -> ParsedDocument: ...
