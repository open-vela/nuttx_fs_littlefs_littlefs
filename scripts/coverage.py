#!/usr/bin/env python3
#
# Parse and report coverage info from .info files generated by lcov
#
import os
import glob
import csv
import re
import collections as co
import bisect as b


INFO_PATHS = ['tests/*.toml.info']

def collect(paths, **args):
    file = None
    funcs = []
    lines = co.defaultdict(lambda: 0)
    pattern = re.compile(
        '^(?P<file>SF:/?(?P<file_name>.*))$'
        '|^(?P<func>FN:(?P<func_lineno>[0-9]*),(?P<func_name>.*))$'
        '|^(?P<line>DA:(?P<line_lineno>[0-9]*),(?P<line_hits>[0-9]*))$')
    for path in paths:
        with open(path) as f:
            for line in f:
                m = pattern.match(line)
                if m and m.group('file'):
                    file = m.group('file_name')
                elif m and file and m.group('func'):
                    funcs.append((file, int(m.group('func_lineno')),
                        m.group('func_name')))
                elif m and file and m.group('line'):
                    lines[(file, int(m.group('line_lineno')))] += (
                        int(m.group('line_hits')))

    # map line numbers to functions
    funcs.sort()
    def func_from_lineno(file, lineno):
        i = b.bisect(funcs, (file, lineno))
        if i and funcs[i-1][0] == file:
            return funcs[i-1][2]
        else:
            return None

    # reduce to function info
    reduced_funcs = co.defaultdict(lambda: (0, 0))
    for (file, line_lineno), line_hits in lines.items():
        func = func_from_lineno(file, line_lineno)
        if not func:
            continue
        hits, count = reduced_funcs[(file, func)]
        reduced_funcs[(file, func)] = (hits + (line_hits > 0), count + 1)

    results = []
    for (file, func), (hits, count) in reduced_funcs.items():
        # discard internal/testing functions (test_* injected with
        # internal testing)
        if not args.get('everything'):
            if func.startswith('__') or func.startswith('test_'):
                continue
        # discard .8449 suffixes created by optimizer
        func = re.sub('\.[0-9]+', '', func)
        results.append((file, func, hits, count))

    return results


def main(**args):
    # find coverage
    if not args.get('use'):
        # find *.info files
        paths = []
        for path in args['info_paths']:
            if os.path.isdir(path):
                path = path + '/*.gcov'

            for path in glob.glob(path):
                paths.append(path)

        if not paths:
            print('no .info files found in %r?' % args['info_paths'])
            sys.exit(-1)

        results = collect(paths, **args)
    else:
        with open(args['use']) as f:
            r = csv.DictReader(f)
            results = [
                (   result['file'],
                    result['function'],
                    int(result['coverage_hits']),
                    int(result['coverage_count']))
                for result in r]

    total_hits, total_count = 0, 0
    for _, _, hits, count in results:
        total_hits += hits
        total_count += count

    # find previous results?
    if args.get('diff'):
        try:
            with open(args['diff']) as f:
                r = csv.DictReader(f)
                prev_results = [
                    (   result['file'],
                        result['function'],
                        int(result['coverage_hits']),
                        int(result['coverage_count']))
                    for result in r]
        except FileNotFoundError:
            prev_results = []

        prev_total_hits, prev_total_count = 0, 0
        for _, _, hits, count in prev_results:
            prev_total_hits += hits
            prev_total_count += count

    # write results to CSV
    if args.get('output'):
        with open(args['output'], 'w') as f:
            w = csv.writer(f)
            w.writerow(['file', 'function', 'coverage_hits', 'coverage_count'])
            for file, func, hits, count in sorted(results):
                w.writerow((file, func, hits, count))

    # print results
    def dedup_entries(results, by='function'):
        entries = co.defaultdict(lambda: (0, 0))
        for file, func, hits, count in results:
            entry = (file if by == 'file' else func)
            entry_hits, entry_count = entries[entry]
            entries[entry] = (entry_hits + hits, entry_count + count)
        return entries

    def diff_entries(olds, news):
        diff = co.defaultdict(lambda: (0, 0, 0, 0, 0, 0, 0))
        for name, (new_hits, new_count) in news.items():
            diff[name] = (
                0, 0,
                new_hits, new_count,
                new_hits, new_count,
                (new_hits/new_count if new_count else 1.0) - 1.0)
        for name, (old_hits, old_count) in olds.items():
            _, _, new_hits, new_count, _, _, _ = diff[name]
            diff[name] = (
                old_hits, old_count,
                new_hits, new_count,
                new_hits-old_hits, new_count-old_count,
                ((new_hits/new_count if new_count else 1.0)
                    - (old_hits/old_count if old_count else 1.0)))
        return diff

    def sorted_entries(entries):
        if args.get('coverage_sort'):
            return sorted(entries, key=lambda x: (-(x[1][0]/x[1][1] if x[1][1] else -1), x))
        elif args.get('reverse_coverage_sort'):
            return sorted(entries, key=lambda x: (+(x[1][0]/x[1][1] if x[1][1] else -1), x))
        else:
            return sorted(entries)

    def sorted_diff_entries(entries):
        if args.get('coverage_sort'):
            return sorted(entries, key=lambda x: (-(x[1][2]/x[1][3] if x[1][3] else -1), x))
        elif args.get('reverse_coverage_sort'):
            return sorted(entries, key=lambda x: (+(x[1][2]/x[1][3] if x[1][3] else -1), x))
        else:
            return sorted(entries, key=lambda x: (-x[1][6], x))

    def print_header(by=''):
        if not args.get('diff'):
            print('%-36s %19s' % (by, 'hits/line'))
        else:
            print('%-36s %19s %19s %11s' % (by, 'old', 'new', 'diff'))

    def print_entry(name, hits, count):
        print("%-36s %11s %7s" % (name,
            '%d/%d' % (hits, count)
                if count else '-',
            '%.1f%%' % (100*hits/count)
                if count else '-'))

    def print_diff_entry(name,
            old_hits, old_count,
            new_hits, new_count,
            diff_hits, diff_count,
            ratio):
        print("%-36s %11s %7s %11s %7s %11s%s" % (name,
            '%d/%d' % (old_hits, old_count)
                if old_count else '-',
            '%.1f%%' % (100*old_hits/old_count)
                if old_count else '-',
            '%d/%d' % (new_hits, new_count)
                if new_count else '-',
            '%.1f%%' % (100*new_hits/new_count)
                if new_count else '-',
            '%+d/%+d' % (diff_hits, diff_count),
            ' (%+.1f%%)' % (100*ratio) if ratio else ''))

    def print_entries(by='function'):
        entries = dedup_entries(results, by=by)

        if not args.get('diff'):
            print_header(by=by)
            for name, (hits, count) in sorted_entries(entries.items()):
                print_entry(name, hits, count)
        else:
            prev_entries = dedup_entries(prev_results, by=by)
            diff = diff_entries(prev_entries, entries)
            print_header(by='%s (%d added, %d removed)' % (by,
                sum(1 for _, old, _, _, _, _, _ in diff.values() if not old),
                sum(1 for _, _, _, new, _, _, _ in diff.values() if not new)))
            for name, (
                    old_hits, old_count,
                    new_hits, new_count,
                    diff_hits, diff_count, ratio) in sorted_diff_entries(
                        diff.items()):
                if ratio or args.get('all'):
                    print_diff_entry(name,
                        old_hits, old_count,
                        new_hits, new_count,
                        diff_hits, diff_count,
                        ratio)

    def print_totals():
        if not args.get('diff'):
            print_entry('TOTAL', total_hits, total_count)
        else:
            ratio = ((total_hits/total_count
                    if total_count else 1.0)
                - (prev_total_hits/prev_total_count
                    if prev_total_count else 1.0))
            print_diff_entry('TOTAL',
                prev_total_hits, prev_total_count,
                total_hits, total_count,
                total_hits-prev_total_hits, total_count-prev_total_count,
                ratio)

    if args.get('quiet'):
        pass
    elif args.get('summary'):
        print_header()
        print_totals()
    elif args.get('files'):
        print_entries(by='file')
        print_totals()
    else:
        print_entries(by='function')
        print_totals()

if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        description="Parse and report coverage info from .info files \
            generated by lcov")
    parser.add_argument('info_paths', nargs='*', default=INFO_PATHS,
        help="Description of where to find *.info files. May be a directory \
            or list of paths. *.info files will be merged to show the total \
            coverage. Defaults to %r." % INFO_PATHS)
    parser.add_argument('-v', '--verbose', action='store_true',
        help="Output commands that run behind the scenes.")
    parser.add_argument('-o', '--output',
        help="Specify CSV file to store results.")
    parser.add_argument('-u', '--use',
        help="Don't do any work, instead use this CSV file.")
    parser.add_argument('-d', '--diff',
        help="Specify CSV file to diff code size against.")
    parser.add_argument('-a', '--all', action='store_true',
        help="Show all functions, not just the ones that changed.")
    parser.add_argument('-A', '--everything', action='store_true',
        help="Include builtin and libc specific symbols.")
    parser.add_argument('-s', '--coverage-sort', action='store_true',
        help="Sort by coverage.")
    parser.add_argument('-S', '--reverse-coverage-sort', action='store_true',
        help="Sort by coverage, but backwards.")
    parser.add_argument('--files', action='store_true',
        help="Show file-level coverage.")
    parser.add_argument('--summary', action='store_true',
        help="Only show the total coverage.")
    parser.add_argument('-q', '--quiet', action='store_true',
        help="Don't show anything, useful with -o.")
    parser.add_argument('--build-dir',
        help="Specify the relative build directory. Used to map object files \
            to the correct source files.")
    sys.exit(main(**vars(parser.parse_args())))
