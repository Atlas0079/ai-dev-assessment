"""Export shareable internal source, excluding submissions, credentials and runtimes."""
from pathlib import Path
import zipfile
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from scripts.pack_contracts import candidate_files
excluded={'.runtime','data','node_modules','target','__pycache__','.git','releases'}
output=root/'releases/assessment-tools-source.zip'
output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob('*')):
        relative=p.relative_to(root)
        if not p.is_file() or any(part in excluded for part in relative.parts):continue
        # Only the canonical internal answer tree belongs in a source release.
        if relative.parts[0]=='internal' and (len(relative.parts)<2 or relative.parts[1]!='examples'):continue
        if p.suffix=='.pyc' or p.name.startswith('.env'):continue
        z.write(p,Path(root.name)/relative)
    # Public sources are a runtime dependency of the shared WORKFLOW modules and
    # the input for rebuilding the single exam ZIP after deployment.
    for name, content in candidate_files().items():
        if name != '题目目录.json':
            z.writestr('candidate/' + name, content)
print(output)
