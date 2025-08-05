import json, subprocess, tempfile, logging
from pathlib import Path
from typing import Dict, List, Any

def run_semgrep(code_root: Path, config: Path, results_file: Path) -> List[Dict[str, Any]]:
    cmd = ["semgrep", "--config", str(config), "--json", "--output", str(results_file), str(code_root)]
    logging.info("▶️  Running: %s", " ".join(cmd))
    completed = subprocess.run(cmd, text=True, capture_output=True)
    if completed.returncode not in (0, 1):
        logging.error(completed.stderr)
        raise RuntimeError("Semgrep failed")
    return json.loads(results_file.read_text()).get("results", [])
