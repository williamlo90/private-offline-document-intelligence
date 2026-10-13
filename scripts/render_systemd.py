"""Render inactive Linux service templates for an explicit release path."""
import argparse
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def render(root,release,output):
    if not re.fullmatch(r'/[A-Za-z0-9/_-]+',root) or '..' in Path(root).parts:
        raise ValueError('Use an absolute Linux installation path without spaces')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',release):
        raise ValueError('Invalid release name')
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'local') or output.exists():
        raise ValueError('Output must be a new directory inside project local')
    output.mkdir(parents=True)
    for template in sorted((ROOT/'deploy/systemd').glob('*.service.template')):
        content=template.read_text().replace('@ROOT@',root.rstrip('/')).replace('@RELEASE@',release)
        (output/template.name.removesuffix('.template')).write_text(content)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    parser.add_argument('--release',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(render(args.root,args.release,args.output))
