"""File helpers for standalone checks; no candidate or workflow records."""
import hashlib,json,os,stat,uuid,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]

def save(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(temp,path)
def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def safe_extract(blob,destination):
    if len(blob)>100*1024*1024: raise ValueError('压缩包超过100MB')
    import io
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        infos=z.infolist()
        if len(infos)>10000 or sum(x.file_size for x in infos)>500*1024*1024: raise ValueError('解压体积或文件数超限')
        seen=set()
        for x in infos:
            path=PurePosixPath(x.filename.replace('\\','/'))
            if path.is_absolute() or any(p in ('..','') or ':' in p for p in path.parts) or not path.parts: raise ValueError('非法归档路径')
            if stat.S_ISLNK(x.external_attr>>16): raise ValueError('不允许符号链接')
            key=str(path).casefold()
            if key in seen: raise ValueError('重复归档路径')
            seen.add(key)
            if any(p.rstrip(' .')!=p for p in path.parts): raise ValueError('非法文件名')
        z.extractall(destination)