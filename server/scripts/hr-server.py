"""Run the HR upload and report service."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.runtime/pythonlibs'))
from assessment.hr_jobs import JobStore
from assessment.hr_service import HRServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8088, type=int)
    parser.add_argument('--data', type=Path, default=ROOT / '.runtime/hr')
    parser.add_argument('--secure-cookie', action='store_true', help='Use behind an HTTPS reverse proxy')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 13):
        parser.error('固定环境的源码检查需要 Python 3.13，请使用该版本运行服务。')
    store = JobStore(args.data)
    server = HRServer((args.host, args.port), store, os.environ.get('HR_ACCESS_PASSWORD', ''), args.secure_cookie)
    store.start()
    print(f'HR service: http://{args.host}:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
        server.server_close()


if __name__ == '__main__':
    main()
