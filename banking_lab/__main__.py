import argparse
import json
from pathlib import Path

from .analysis import analyze
from .generate import generate
from .pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description='Synthetic South African banking analytics lab')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('demo', 'generate'):
        command = commands.add_parser(name)
        command.add_argument('--workspace', type=Path, default=Path('build'))
    ingest = commands.add_parser('ingest')
    ingest.add_argument('--database', type=Path, required=True)
    ingest.add_argument('--batch', type=Path, required=True)
    ingest.add_argument('--exports', type=Path, required=True)
    report = commands.add_parser('analyze')
    report.add_argument('--database', type=Path, required=True)
    report.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command in ('generate', 'demo'):
        database = generate(args.workspace)
        if args.command == 'demo':
            analyze(database, args.workspace / 'baseline')
            first = run_pipeline(database, args.workspace / 'next_batch.json', args.workspace / 'exports')
            second = run_pipeline(database, args.workspace / 'next_batch.json', args.workspace / 'exports')
            if second['counts']['inserted'] or second['counts']['revised']:
                raise RuntimeError('repeat_delivery_changed_raw_history')
            analyze(database, args.workspace / 'report')
            print(json.dumps({'first_load': first['counts'], 'repeat_load': second['counts'],
                              'report': str(args.workspace / 'report/index.html')}, indent=2))
        else:
            print(database)
    elif args.command == 'ingest':
        print(json.dumps(run_pipeline(args.database, args.batch, args.exports), indent=2))
    else:
        analyze(args.database, args.output)
        print(args.output / 'index.html')


if __name__ == '__main__':
    main()
