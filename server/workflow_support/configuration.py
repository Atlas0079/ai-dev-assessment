"""Trusted WORKFLOW defaults shared by runners, setup tools and the model proxy."""
import json
from pathlib import Path


DEFAULT_CONFIG = (Path(__file__).resolve().parents[2] /
                  'candidate/tasks/WORKFLOW/WORKFLOW/workflow.config.json')


def effective_config(*, business_url=None, model_url=None):
    # Read afresh so every caller owns its configuration and overrides cannot
    # mutate a cached default or the candidate's original configuration file.
    config = json.loads(DEFAULT_CONFIG.read_text(encoding='utf-8-sig'))
    if config.get('schemaVersion') != '1.0' or config['llm']['protocol'] != 'chat_completions':
        raise ValueError('WORKFLOW 固定配置无效')
    if business_url is not None:
        config['business']['base_url'] = business_url.rstrip('/')
    if model_url is not None:
        config['llm']['base_url'] = model_url.rstrip('/')
    return config
