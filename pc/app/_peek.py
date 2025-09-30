from pathlib import Path
lines = Path('capture.py').read_text().splitlines()
for line in lines[:16]:
    print(repr(line))
