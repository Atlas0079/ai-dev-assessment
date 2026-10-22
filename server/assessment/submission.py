"""Submission identity comes from the ZIP name; selected tasks come from directories."""
import re
from pathlib import Path

from .catalog import QUESTIONS

FORMAT = 'filename-v1'
NAME = re.compile(r'([^_]{1,50})_(1[3-9][0-9]{9})_v([1-9][0-9]{0,6})\.zip\Z', re.IGNORECASE)


def parse_filename(filename):
    match = NAME.fullmatch(filename) if isinstance(filename, str) else None
    if match:
        name, phone, version = match.groups()
        if (name == name.strip() and any(char.isalpha() for char in name)
                and all(char.isalpha() or char in '· .-' for char in name)
                and int(version) <= 1000000):
            return name + '_' + phone, int(version)
    raise ValueError('答案 ZIP 请命名为“姓名_11位报名手机号_v1.zip”，例如“张三_13800138000_v1.zip”；补交时增加版本。')


def submitted_tasks(source):
    source = Path(source)
    tasks = [task for task in QUESTIONS if (source / task).is_dir()]
    if not tasks:
        raise ValueError('ZIP 根目录至少需要一个题目工程目录：' + '、'.join(QUESTIONS) + '。')
    unexpected = [path.name for path in source.iterdir()
                  if path.name not in {*tasks, 'README.md'}
                  or (path.name == 'README.md' and not path.is_file())]
    if unexpected:
        raise ValueError('ZIP 根目录只接收 ' + '、'.join(QUESTIONS) + ' 题目工程和可选的 README.md：' + '、'.join(sorted(unexpected)))
    return tasks
