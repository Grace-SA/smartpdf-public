"""Explicit opt-in local harness; not imported or used by production."""
import argparse,os,sys
from pathlib import Path
from supervised_job import run
p=argparse.ArgumentParser();p.add_argument('--enable-research',action='store_true');p.add_argument('source');p.add_argument('output');a=p.parse_args()
if not a.enable_research:p.error('Disabled by default; explicit --enable-research is required')
r=Path(__file__).resolve().parent
if not (r/'engine-lock.json').is_file() or not (r/'engine/convert.py').is_file():p.error('Run prepare.py first')
raise SystemExit(run([sys.executable,str(r/'engine/convert.py'),a.source,a.output,'{"ocr":true}']))
