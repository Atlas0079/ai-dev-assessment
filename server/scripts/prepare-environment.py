"""Prepare the public fixed dependencies and private WORKFLOW services for HR."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.environment import EnvironmentUnavailable, verify
from assessment.workflow_environment import prepare_services, verify_services
from fixed_runtime import prepare

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify'), nargs='?', default='prepare')
    args = parser.parse_args()
    try:
        if args.action == 'prepare':
            prepare()
            prepare_services()
        else:
            print(json.dumps({'public': verify(), 'workflow': verify_services()}, ensure_ascii=False, indent=2))
    except EnvironmentUnavailable as error:
        parser.exit(1, str(error) + '\n')
