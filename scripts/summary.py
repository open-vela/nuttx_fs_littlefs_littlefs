#!/usr/bin/env python3
#
# Script to summarize the outputs of other scripts. Operates on CSV files.
#

import collections as co
import csv
import functools as ft
import glob
import math as m
import os
import re


CSV_PATHS = ['*.csv']

# Defaults are common fields generated by other littlefs scripts
MERGES = {
    'add': (
        ['code_size', 'data_size', 'stack_frame', 'struct_size',
            'coverage_lines', 'coverage_branches'],
        lambda xs: sum(xs[1:], start=xs[0])
    ),
    'mul': (
        [],
        lambda xs: m.prod(xs[1:], start=xs[0])
    ),
    'min': (
        [],
        min
    ),
    'max': (
        ['stack_limit', 'coverage_hits'],
        max
    ),
    'avg': (
        [],
        lambda xs: sum(xs[1:], start=xs[0]) / len(xs)
    ),
}


def openio(path, mode='r'):
    if path == '-':
        if 'r' in mode:
            return os.fdopen(os.dup(sys.stdin.fileno()), 'r')
        else:
            return os.fdopen(os.dup(sys.stdout.fileno()), 'w')
    else:
        return open(path, mode)


# integer fields
class IntField(co.namedtuple('IntField', 'x')):
    __slots__ = ()
    def __new__(cls, x):
        if isinstance(x, IntField):
            return x
        if isinstance(x, str):
            try:
                x = int(x, 0)
            except ValueError:
                # also accept +-∞ and +-inf
                if re.match('^\s*\+?\s*(?:∞|inf)\s*$', x):
                    x = float('inf')
                elif re.match('^\s*-\s*(?:∞|inf)\s*$', x):
                    x = float('-inf')
                else:
                    raise
        return super().__new__(cls, x)

    def __int__(self):
        assert not m.isinf(self.x)
        return self.x

    def __float__(self):
        return float(self.x)

    def __str__(self):
        if self.x == float('inf'):
            return '∞'
        elif self.x == float('-inf'):
            return '-∞'
        else:
            return str(self.x)

    none = '%7s' % '-'
    def table(self):
        return '%7s' % (self,)

    diff_none = '%7s' % '-'
    diff_table = table

    def diff_diff(self, other):
        new = self.x if self else 0
        old = other.x if other else 0
        diff = new - old
        if diff == float('+inf'):
            return '%7s' % '+∞'
        elif diff == float('-inf'):
            return '%7s' % '-∞'
        else:
            return '%+7d' % diff

    def ratio(self, other):
        new = self.x if self else 0
        old = other.x if other else 0
        if m.isinf(new) and m.isinf(old):
            return 0.0
        elif m.isinf(new):
            return float('+inf')
        elif m.isinf(old):
            return float('-inf')
        elif not old and not new:
            return 0.0
        elif not old:
            return 1.0
        else:
            return (new-old) / old

    def __add__(self, other):
        return IntField(self.x + other.x)

    def __mul__(self, other):
        return IntField(self.x * other.x)

    def __lt__(self, other):
        return self.x < other.x

    def __gt__(self, other):
        return self.__class__.__lt__(other, self)

    def __le__(self, other):
        return not self.__gt__(other)

    def __ge__(self, other):
        return not self.__lt__(other)

    def __truediv__(self, n):
        if m.isinf(self.x):
            return self
        else:
            return IntField(round(self.x / n))

# float fields
class FloatField(co.namedtuple('FloatField', 'x')):
    __slots__ = ()
    def __new__(cls, x):
        if isinstance(x, FloatField):
            return x
        if isinstance(x, str):
            try:
                x = float(x)
            except ValueError:
                # also accept +-∞ and +-inf
                if re.match('^\s*\+?\s*(?:∞|inf)\s*$', x):
                    x = float('inf')
                elif re.match('^\s*-\s*(?:∞|inf)\s*$', x):
                    x = float('-inf')
                else:
                    raise
        return super().__new__(cls, x)

    def __float__(self):
        return float(self.x)

    def __str__(self):
        if self.x == float('inf'):
            return '∞'
        elif self.x == float('-inf'):
            return '-∞'
        else:
            return '%.1f' % self.x

    none = IntField.none
    table = IntField.table
    diff_none = IntField.diff_none
    diff_table = IntField.diff_table
    diff_diff = IntField.diff_diff
    ratio = IntField.ratio
    __add__ = IntField.__add__
    __mul__ = IntField.__mul__
    __lt__ = IntField.__lt__
    __gt__ = IntField.__gt__
    __le__ = IntField.__le__
    __ge__ = IntField.__ge__

    def __truediv__(self, n):
        if m.isinf(self.x):
            return self
        else:
            return FloatField(self.x / n)

# fractional fields, a/b
class FracField(co.namedtuple('FracField', 'a,b')):
    __slots__ = ()
    def __new__(cls, a, b=None):
        if isinstance(a, FracField) and b is None:
            return a
        if isinstance(a, str) and b is None:
            a, b = a.split('/', 1)
        if b is None:
            b = a
        return super().__new__(cls, IntField(a), IntField(b))

    def __str__(self):
        return '%s/%s' % (self.a, self.b)

    none = '%11s %7s' % ('-', '-')
    def table(self):
        if not self.b.x:
            return self.none

        t = self.a.x/self.b.x
        return '%11s %7s' % (
            self,
            '∞%' if t == float('+inf')
            else '-∞%' if t == float('-inf')
            else '%.1f%%' % (100*t))

    diff_none = '%11s' % '-'
    def diff_table(self):
        if not self.b.x:
            return self.diff_none

        return '%11s' % (self,)

    def diff_diff(self, other):
        new_a, new_b = self if self else (IntField(0), IntField(0))
        old_a, old_b = other if other else (IntField(0), IntField(0))
        return '%11s' % ('%s/%s' % (
            new_a.diff_diff(old_a).strip(),
            new_b.diff_diff(old_b).strip()))

    def ratio(self, other):
        new_a, new_b = self if self else (IntField(0), IntField(0))
        old_a, old_b = other if other else (IntField(0), IntField(0))
        new = new_a.x/new_b.x if new_b.x else 1.0
        old = old_a.x/old_b.x if old_b.x else 1.0
        return new - old

    def __add__(self, other):
        return FracField(self.a + other.a, self.b + other.b)

    def __mul__(self, other):
        return FracField(self.a * other.a, self.b + other.b)

    def __lt__(self, other):
        self_r = self.a.x/self.b.x if self.b.x else float('-inf')
        other_r = other.a.x/other.b.x if other.b.x else float('-inf')
        return self_r < other_r

    def __gt__(self, other):
        return self.__class__.__lt__(other, self)

    def __le__(self, other):
        return not self.__gt__(other)

    def __ge__(self, other):
        return not self.__lt__(other)

    def __truediv__(self, n):
        return FracField(self.a / n, self.b / n)


def homogenize(results, *,
        fields=None,
        merges=None,
        renames=None,
        types=None,
        **_):
    # rename fields?
    if renames is not None:
        results_ = []
        for r in results:
            results_.append({renames.get(k, k): v for k, v in r.items()})
        results = results_

    # find all fields
    if not fields:
        fields = co.OrderedDict()
        for r in results:
            # also remove None fields, these can get introduced by
            # csv.DictReader when header and rows mismatch
            fields.update((k, v) for k, v in r.items() if k is not None)
        fields = list(fields.keys())

    # go ahead and clean up none values, these can have a few forms
    results_ = []
    for r in results:
        results_.append({
            k: r[k] for k in fields
            if r.get(k) is not None and not(
                isinstance(r[k], str)
                and re.match('^\s*[+-]?\s*$', r[k]))})

    # find best type for all fields
    def try_(x, type):
        try:
            type(x)
            return True
        except ValueError:
            return False

    if types is None:
        types = {}
        for k in fields:
            if merges is not None and merges.get(k):
                for type in [IntField, FloatField, FracField]:
                    if all(k not in r or try_(r[k], type) for r in results_):
                        types[k] = type
                        break
                else:
                    print("no type matches field %r?" % k)
                    sys.exit(-1)

    # homogenize types
    for k in fields:
        if k in types:
            for r in results_:
                if k in r:
                    r[k] = types[k](r[k])

    return fields, types, results_


def fold(results, *,
        fields=None,
        merges=None,
        by=None,
        **_):
    folding = co.OrderedDict()
    if by is None:
        by = [k for k in fields if k not in merges]

    for r in results:
        name = tuple(r.get(k) for k in by)
        if name not in folding:
            folding[name] = {k: [] for k in fields if k in merges}
        for k in fields:
            # drop all fields fields without a type
            if k in merges and k in r:
                folding[name][k].append(r[k])

    # merge fields, we need the count at this point for averages
    folded = []
    types = {}
    for name, r in folding.items():
        r_ = {}
        for k, vs in r.items():
            if vs:
                _, merge = MERGES[merges[k]]
                r_[k] = merge(vs)

        # drop all rows without any fields
        # and drop all empty keys
        if r_:
            folded.append(dict(
                {k: n for k, n in zip(by, name) if n},
                **r_))

    fields_ = by + [k for k in fields if k in merges]
    return fields_, folded


def table(results, diff_results=None, *,
        fields=None,
        types=None,
        merges=None,
        by=None,
        sort=None,
        reverse_sort=None,
        summary=False,
        all=False,
        percent=False,
        **_):
    all_, all = all, __builtins__.all

    # fold
    if by is not None:
        fields, results = fold(results, fields=fields, merges=merges, by=by)
        if diff_results is not None:
            _, diff_results = fold(diff_results,
                fields=fields, merges=merges, by=by)

    table = {
        tuple(r.get(k,'') for k in fields if k not in merges): r
        for r in results}
    diff_table = {
        tuple(r.get(k,'') for k in fields if k not in merges): r
        for r in diff_results or []}

    # sort, note that python's sort is stable
    names = list(table.keys() | diff_table.keys())
    names.sort()
    if diff_results is not None:
        names.sort(key=lambda n: [
            -types[k].ratio(
                table.get(n,{}).get(k),
                diff_table.get(n,{}).get(k))
                for k in fields if k in merges])
    if sort:
        names.sort(key=lambda n: tuple(
            (table[n][k],) if k in table.get(n,{}) else ()
            for k in sort),
            reverse=True)
    elif reverse_sort:
        names.sort(key=lambda n: tuple(
            (table[n][k],) if k in table.get(n,{}) else ()
            for k in reverse_sort),
            reverse=False)

    # print header
    print('%-36s' % ('%s%s' % (
        ','.join(k for k in fields if k not in merges),
        ' (%d added, %d removed)' % (
            sum(1 for n in table if n not in diff_table),
            sum(1 for n in diff_table if n not in table))
            if diff_results is not None and not percent else '')
        if not summary else ''),
        end='')
    if diff_results is None:
        print(' %s' % (
            ' '.join(k.rjust(len(types[k].none))
                for k in fields if k in merges)))
    elif percent:
        print(' %s' % (
            ' '.join(k.rjust(len(types[k].diff_none))
                for k in fields if k in merges)))
    else:
        print(' %s %s %s' % (
            ' '.join(('o'+k).rjust(len(types[k].diff_none))
                for k in fields if k in merges),
            ' '.join(('n'+k).rjust(len(types[k].diff_none))
                for k in fields if k in merges),
            ' '.join(('d'+k).rjust(len(types[k].diff_none))
                for k in fields if k in merges)))

    # print entries
    if not summary:
        for name in names:
            r = table.get(name, {})
            if diff_results is not None:
                diff_r = diff_table.get(name, {})
                ratios = [types[k].ratio(r.get(k), diff_r.get(k))
                    for k in fields if k in merges]
                if not any(ratios) and not all_:
                    continue

            print('%-36s' % ','.join(name), end='')
            if diff_results is None:
                print(' %s' % (
                    ' '.join(r[k].table()
                        if k in r else types[k].none
                        for k in fields if k in merges)))
            elif percent:
                print(' %s%s' % (
                    ' '.join(r[k].diff_table()
                        if k in r else types[k].diff_none
                        for k in fields if k in merges),
                    ' (%s)' % ', '.join(
                            '+∞%' if t == float('+inf')
                            else '-∞%' if t == float('-inf')
                            else '%+.1f%%' % (100*t)
                            for t in ratios)))
            else:
                print(' %s %s %s%s' % (
                    ' '.join(diff_r[k].diff_table()
                        if k in diff_r else types[k].diff_none
                        for k in fields if k in merges),
                    ' '.join(r[k].diff_table()
                        if k in r else types[k].diff_none
                        for k in fields if k in merges),
                    ' '.join(types[k].diff_diff(r.get(k), diff_r.get(k))
                        if k in r or k in diff_r else types[k].diff_none
                        for k in fields if k in merges),
                    ' (%s)' % ', '.join(
                            '+∞%' if t == float('+inf')
                            else '-∞%' if t == float('-inf')
                            else '%+.1f%%' % (100*t)
                            for t in ratios
                            if t)
                        if any(ratios) else ''))

    # print total
    _, total = fold(results, fields=fields, merges=merges, by=[])
    r = total[0] if total else {}
    if diff_results is not None:
        _, diff_total = fold(diff_results,
            fields=fields, merges=merges, by=[])
        diff_r = diff_total[0] if diff_total else {}
        ratios = [types[k].ratio(r.get(k), diff_r.get(k))
            for k in fields if k in merges]

    print('%-36s' % 'TOTAL', end='')
    if diff_results is None:
        print(' %s' % (
            ' '.join(r[k].table()
                if k in r else types[k].none
                for k in fields if k in merges)))
    elif percent:
        print(' %s%s' % (
            ' '.join(r[k].diff_table()
                if k in r else types[k].diff_none
                for k in fields if k in merges),
            ' (%s)' % ', '.join(
                    '+∞%' if t == float('+inf')
                    else '-∞%' if t == float('-inf')
                    else '%+.1f%%' % (100*t)
                    for t in ratios)))
    else:
        print(' %s %s %s%s' % (
            ' '.join(diff_r[k].diff_table()
                if k in diff_r else types[k].diff_none
                for k in fields if k in merges),
            ' '.join(r[k].diff_table()
                if k in r else types[k].diff_none
                for k in fields if k in merges),
            ' '.join(types[k].diff_diff(r.get(k), diff_r.get(k))
                if k in r or k in diff_r else types[k].diff_none
                for k in fields if k in merges),
            ' (%s)' % ', '.join(
                    '+∞%' if t == float('+inf')
                    else '-∞%' if t == float('-inf')
                    else '%+.1f%%' % (100*t)
                    for t in ratios
                    if t)
                if any(ratios) else ''))


def main(csv_paths, *, fields=None, by=None, **args):
    # figure out what fields to use
    renames = {}

    if fields is not None:
        fields_ = []
        for name in fields:
            if '=' in name:
                a, b = name.split('=', 1)
                renames[b] = a
                name = a
            fields_.append(name)
        fields = fields_

    if by is not None:
        by_ = []
        for name in by:
            if '=' in name:
                a, b = name.split('=', 1)
                renames[b] = a
                name = a
            by_.append(name)
        by = by_

    # include 'by' fields in fields, it doesn't make sense to not
    if fields is not None and by is not None:
        fields[:0] = [k for k in by if k not in fields]

    # use preconfigured merge operations unless any merge operation is
    # explictly specified
    merge_args = (args
        if any(args.get(m) for m in MERGES.keys())
        else {m: k for m, (k, _) in MERGES.items()})
    merges = {}
    for m in MERGES.keys():
        for k in merge_args.get(m, []):
            if k in merges:
                print("conflicting merge type for field %r?" % k)
                sys.exit(-1)
            merges[k] = m
    # allow renames to apply to merges
    for m in MERGES.keys():
        for k in merge_args.get(m, []):
            if renames.get(k, k) not in merges:
                merges[renames.get(k, k)] = m
    # ignore merges that conflict with 'by' fields
    if by is not None:
        for k in by:
            if k in merges:
                del merges[k]

    # find CSV files
    paths = []
    for path in csv_paths:
        if os.path.isdir(path):
            path = path + '/*.csv'

        for path in glob.glob(path):
            paths.append(path)

    if not paths:
        print('no .csv files found in %r?' % csv_paths)
        sys.exit(-1)

    results = []
    for path in paths:
        try:
            with openio(path) as f:
                reader = csv.DictReader(f)
                for r in reader:
                    results.append(r)
        except FileNotFoundError:
            pass

    # homogenize
    fields, types, results = homogenize(results,
        fields=fields, merges=merges, renames=renames)

    # fold to remove duplicates
    fields, results = fold(results,
        fields=fields, merges=merges)

    # write results to CSV
    if args.get('output'):
        with openio(args['output'], 'w') as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            for r in results:
                writer.writerow(r)

    # find previous results?
    if args.get('diff'):
        diff_results = []
        try:
            with openio(args['diff']) as f:
                reader = csv.DictReader(f)
                for r in reader:
                    diff_results.append(r)
        except FileNotFoundError:
            pass

        # homogenize
        _, _, diff_results = homogenize(diff_results,
            fields=fields, merges=merges, renames=renames, types=types)

        # fold to remove duplicates
        _, diff_results = fold(diff_results,
            fields=fields, merges=merges)

    # print table
    if not args.get('quiet'):
        table(
            results,
            diff_results if args.get('diff') else None,
            fields=fields,
            types=types,
            merges=merges,
            by=by,
            **args)


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        description="Summarize measurements in CSV files.")
    parser.add_argument(
        'csv_paths',
        nargs='*',
        default=CSV_PATHS,
        help="Description of where to find *.csv files. May be a directory "
            "or list of paths. Defaults to %(default)r.")
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help="Don't show anything, useful with -o.")
    parser.add_argument(
        '-o', '--output',
        help="Specify CSV file to store results.")
    parser.add_argument(
        '-d', '--diff',
        help="Specify CSV file to diff against.")
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help="Show all, not just the ones that changed.")
    parser.add_argument(
        '-p', '--percent',
        action='store_true',
        help="Only show percentage change, not a full diff.")
    parser.add_argument(
        '-f', '--fields',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Only show these fields. Can rename fields "
            "with old_name=new_name.")
    parser.add_argument(
        '-b', '--by',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Group by these fields. Can rename fields "
            "with old_name=new_name.")
    parser.add_argument(
        '--add',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Add these fields when merging.")
    parser.add_argument(
        '--mul',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Multiply these fields when merging.")
    parser.add_argument(
        '--min',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Take the minimum of these fields when merging.")
    parser.add_argument(
        '--max',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Take the maximum of these fields when merging.")
    parser.add_argument(
        '--avg',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Average these fields when merging.")
    parser.add_argument(
        '-s', '--sort',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Sort by these fields.")
    parser.add_argument(
        '-S', '--reverse-sort',
        type=lambda x: [x.strip() for x in x.split(',')],
        help="Sort by these fields, but backwards.")
    parser.add_argument(
        '-Y', '--summary',
        action='store_true',
        help="Only show the totals.")
    sys.exit(main(**{k: v
        for k, v in vars(parser.parse_args()).items()
        if v is not None}))
