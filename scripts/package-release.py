"""Export shareable internal source, excluding submissions, credentials and runtimes."""
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[1]
excluded={'.runtime','data','node_modules','target','__pycache__','.git','releases'}
output=root/'releases/assessment-tools-source.zip'
output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob('*')):
        relative=p.relative_to(root)
        if not p.is_file() or any(part in excluded for part in relative.parts):continue
        if p.suffix=='.pyc' or p.name.startswith('.env'):continue
        z.write(p,Path(root.name)/relative)
print(output)
