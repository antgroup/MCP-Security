import re
from pathlib import Path
import sys

def extract_descriptions(root_dir):

    desc_pattern = re.compile(
        r'\bdescription\b\s*[:=]\s*(?P<quote>["\']{3}|["\'])(?P<text>.*?)(?P=quote)',
        flags=re.IGNORECASE | re.DOTALL
    )

    descriptions = []
    for py_file in Path(root_dir).rglob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue

        for match in desc_pattern.finditer(content):
            desc_text = match.group('text').strip()
            if desc_text:
                descriptions.append(desc_text)

    return descriptions

    


