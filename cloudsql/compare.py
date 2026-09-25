import pandas as pd


def _normalise(df, columns):
    """Compare values as text so 1 and 1.0 (a column with NULLs becomes float) count as equal."""
    out = pd.DataFrame(index=df.index)
    for col in columns:
        series = df[col]
        if pd.api.types.is_float_dtype(series):
            out[col] = series.map(lambda v: '' if pd.isna(v) else (str(int(v)) if float(v).is_integer() else repr(v)))
        else:
            out[col] = series.astype(object).where(series.notna(), '').astype(str)
    return out


def compare_frames(a, b, a_name, b_name):
    """Row-by-row comparison of two query results on their common columns. Duplicate rows are matched one to one."""
    common = [c for c in a.columns if c in b.columns]
    result = {
        'rows_a': len(a), 'rows_b': len(b),
        'only_cols_a': [c for c in a.columns if c not in b.columns],
        'only_cols_b': [c for c in b.columns if c not in a.columns],
    }
    if not common:
        raise ValueError('The two results have no column names in common')

    left, right = _normalise(a, common), _normalise(b, common)
    left['__n'] = left.groupby(common).cumcount()
    right['__n'] = right.groupby(common).cumcount()
    merged = left.merge(right, on=common + ['__n'], how='outer', indicator=True)

    only_a = merged[merged['_merge'] == 'left_only'].drop(columns=['__n', '_merge'])
    only_b = merged[merged['_merge'] == 'right_only'].drop(columns=['__n', '_merge'])
    result['same'] = int((merged['_merge'] == 'both').sum())
    result['only_a'] = len(only_a)
    result['only_b'] = len(only_b)
    only_a.insert(0, 'Found only in', a_name)
    only_b.insert(0, 'Found only in', b_name)
    result['diff'] = pd.concat([only_a, only_b], ignore_index=True)
    return result
