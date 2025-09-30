from pathlib import Path

path = Path('session_manager.py')
lines = path.read_text().splitlines()
tick = chr(96)

for idx, line in enumerate(lines):
    if line.strip().startswith('*') and '`True`' in line:
        lines[idx] = f"* {tick}{tick}True{tick}{tick} -> :class:{tick}TestCapture{tick} replays static images from"
        lines[idx + 1] = f"  {tick}{tick}test_source_dir{tick}{tick} for deterministic runs."
        lines[idx + 2] = f"* {tick}{tick}False{tick}{tick} -> :class:{tick}OpenCvCapture{tick} reads frames from a physical camera"
        lines[idx + 3] = "  or Basler via `pypylon` when integrated."
        break

path.write_text('\n'.join(lines) + '\n')
