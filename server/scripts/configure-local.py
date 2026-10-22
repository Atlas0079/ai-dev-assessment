"""Configure trusted reference tools without changing system-wide PATH."""
import argparse,json,os,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1];runtime=root/'.runtime/tools'
java=os.environ.get('JAVA') or next(runtime.glob('jdk8/*/bin/java.exe'),None)
mongo=os.environ.get('MONGOD') or next(runtime.glob('mongodb/*/bin/mongod.exe'),None)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--maven',default=os.environ.get('MAVEN') or shutil.which('mvn'))
p.add_argument('--maven-repository',default=os.environ.get('MAVEN_REPOSITORY',''))
a=p.parse_args()
(root/'.runtime').mkdir(exist_ok=True)
(root/'.runtime/tools.json').write_text(json.dumps({'java':str(java) if java else shutil.which('java'),'mongod':str(mongo) if mongo else shutil.which('mongod'),'maven':a.maven,'maven_repository':a.maven_repository},indent=2),encoding='utf-8')
print((root/'.runtime/tools.json').read_text())
