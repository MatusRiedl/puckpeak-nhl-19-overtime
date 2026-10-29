r"""Build check of the NHL 27 data pack the exe carries: numbers and names only (no textures, audio or EA text blobs),
and it loads. Prints its size and contents; exit 1 on a problem.
    python packaging\check_datapack.py packs\nhl27.json.gz"""
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from overtime_core import nhl27  # noqa: E402
from overtime_roster.app import defaultdb  # noqa: E402

path = sys.argv[1]
size = os.path.getsize(path)
with gzip.open(path, 'rt', encoding='utf-8') as f:
    data = json.load(f)
problems = defaultdb.numbers_only(data, size)
if nhl27.load(path) is None:
    problems.append('nhl27.load refuses it')
counts = ', '.join(f'{k} {len(v)}' for k, v in data.items() if isinstance(v, (list, dict)))
print(f'{os.path.basename(path)}  {size} bytes  format {data.get("format")}  generated {data.get("generated")}  '
      f'({counts})')
for p in problems[:20]:
    print('  problem:', p)
sys.exit(1 if problems else 0)
