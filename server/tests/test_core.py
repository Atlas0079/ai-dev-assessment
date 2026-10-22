import unittest,io,zipfile,tempfile,stat
from pathlib import Path
from assessment.storage import safe_extract

class ArchiveTests(unittest.TestCase):
 def blob(self,name,data='test',mode=None):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   info=zipfile.ZipInfo(name)
   if mode:info.external_attr=mode<<16
   z.writestr(info,data)
  return b.getvalue()
 def test_traversal(self):
  for name in ['../escape','C:/escape','/escape','a/../../escape','a\\..\\escape']:
   with tempfile.TemporaryDirectory() as d:
    with self.assertRaises(ValueError):safe_extract(self.blob(name),Path(d))
 def test_symlinks(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):safe_extract(self.blob('link','target',stat.S_IFLNK|0o777),Path(d))
 def test_valid(self):
  with tempfile.TemporaryDirectory() as d:
   safe_extract(self.blob('ORDER/README.md'),Path(d));self.assertEqual((Path(d)/'ORDER/README.md').read_text(),'test')
if __name__=='__main__':unittest.main()
