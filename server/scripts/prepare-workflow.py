"""Validate submitted configuration and write an explicit assessment override; never executes submission code."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_support.configuration import effective_config

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--project-config', type=Path, required=True)
p.add_argument('--business-url', required=True)
p.add_argument('--model-url', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
config = json.loads(a.project_config.read_text(encoding='utf-8-sig'))
if config.get('schemaVersion') != '1.0' or config.get('llm', {}).get('protocol') != 'chat_completions':
    p.error('Expected schemaVersion 1.0 and chat_completions')
if a.project_config.resolve() == a.output.resolve():
    p.error('Write the assessment override to a different file; preserve the submission')
for url in (a.model_url, a.business_url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        p.error('Invalid base URL')
effective = effective_config(business_url=a.business_url, model_url=a.model_url)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(effective, ensure_ascii=False, indent=2), encoding='utf-8')
print('Set WORKFLOW_CONFIG_PATH to ' + str(a.output.resolve()) + ' and inject WORKFLOW_LLM_API_KEY with the scoped gateway token. No secret was written.')
