"""Configure trusted reference tools without changing system-wide PATH."""
import json,os,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1];runtime=root/'.runtime/tools'
java=os.environ.get('JAVA') or next(runtime.glob('jdk8/*/bin/java.exe'),None)
mongo=os.environ.get('MONGOD') or next(runtime.glob('mongodb/*/bin/mongod.exe'),None)
(root/'.runtime').mkdir(exist_ok=True)
(root/'.runtime/tools.json').write_text(json.dumps({'java':str(java) if java else shutil.which('java'),'mongod':str(mongo) if mongo else shutil.which('mongod')},indent=2),encoding='utf-8')
print((root/'.runtime/tools.json').read_text())
