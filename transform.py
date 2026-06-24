"""Text aggregation/transform utilities."""
import re


def _split_lines(text):
    return [l.strip() for l in text.splitlines() if l.strip()]


def _split_csv(text):
    parts = re.split(r',\s*', text.strip())
    result = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2 and p[0] == p[-1] and p[0] in ('"', "'"):
            p = p[1:-1]
        result.append(p)
    return result


# ── Input type detection ──────────────────────────────────────────────────────

_SQL_KEYWORDS = re.compile(
    r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|WITH|FROM|WHERE|JOIN)\b',
    re.IGNORECASE)

def _is_json_object(text):
    import json
    try:
        v = json.loads(text)
        return isinstance(v, (dict, list))
    except Exception:
        return False

def _is_json_string(text):
    """True if text is a JSON-encoded string literal (quoted, with escapes)."""
    import json
    t = text.strip()
    if not (t.startswith('"') and t.endswith('"')):
        return False
    try:
        v = json.loads(t)
        return isinstance(v, str)
    except Exception:
        return False

def _is_sql(text):
    return bool(_SQL_KEYWORDS.search(text.strip()))


def detect_input_type(text):
    """Return a set of type tags describing the input."""
    text = text.strip()
    if not text:
        return set()

    lines = [l for l in text.splitlines() if l.strip()]
    is_multiline = len(lines) > 1

    types = {'any'}

    if _is_json_object(text):
        types.add('json')
    if _is_json_string(text):
        types.add('json_string')
    if _is_sql(text):
        types.add('sql')

    if is_multiline and not _is_json_object(text):
        types.add('lines')

    if not is_multiline:
        single = text
        if ',' in single:
            types.add('csv')
        if re.match(r'^\(.*\)$', single, re.DOTALL) and ',' in single:
            types.add('sql_in')
        if re.search(r'\s', single):
            types.add('words')

    return types


# ── Beautify ──────────────────────────────────────────────────────────────────

def beautify(text):
    text = text.strip()
    if _is_json_object(text):
        import json
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    if _is_sql(text):
        import sqlparse
        return sqlparse.format(text, reindent=True, keyword_case='upper',
                               identifier_case='lower', strip_comments=False)
    return text


# ── JSON ─────────────────────────────────────────────────────────────────────

def json_stringify(text):
    """Encode text as a JSON string literal (adds surrounding quotes, escapes internals)."""
    import json
    return json.dumps(text)


def json_unstringify(text):
    """Decode a JSON string literal back to plain text (removes surrounding quotes, unescapes)."""
    import json
    t = text.strip()
    try:
        result = json.loads(t)
        if isinstance(result, str):
            return result
        # If it's an object/array, pretty-print it
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception:
        raise ValueError('Input is not a valid JSON string literal')


def json_to_object(text):
    """Convert JSON to a JS object literal with unquoted keys and single-quoted strings."""
    import json, re
    try:
        data = json.loads(text)
    except Exception:
        raise ValueError('Input is not valid JSON')

    def _convert(obj, indent=0):
        pad = '    ' * indent
        inner = '    ' * (indent + 1)
        if isinstance(obj, dict):
            if not obj:
                return '{}'
            lines = []
            for k, v in obj.items():
                key = k if re.match(r'^[A-Za-z_$][A-Za-z0-9_$]*$', k) else f"'{k}'"
                lines.append(f"{inner}{key}: {_convert(v, indent + 1)},")
            return '{\n' + '\n'.join(lines) + '\n' + pad + '}'
        elif isinstance(obj, list):
            if not obj:
                return '[]'
            lines = [f"{inner}{_convert(v, indent + 1)}," for v in obj]
            return '[\n' + '\n'.join(lines) + '\n' + pad + ']'
        elif isinstance(obj, bool):
            return 'true' if obj else 'false'
        elif obj is None:
            return 'null'
        elif isinstance(obj, (int, float)):
            return str(obj)
        else:
            escaped = str(obj).replace('\\', '\\\\').replace("'", "\\'")
            return f"'{escaped}'"

    return _convert(data)


def json_to_values(text):
    """Extract all leaf string values from a JSON object/array, deduplicated."""
    import json
    try:
        data = json.loads(text)
    except Exception:
        raise ValueError('Input is not valid JSON')

    seen = set()
    result = []

    def collect(node):
        if isinstance(node, dict):
            for v in node.values():
                collect(v)
        elif isinstance(node, list):
            for v in node:
                collect(v)
        else:
            s = str(node).strip()
            if s and s not in seen:
                seen.add(s)
                result.append(s)

    collect(data)
    return '\n'.join(result)


# ── Lines → joined ────────────────────────────────────────────────────────────

def lines_to_csv(text, quote=''):
    items = _split_lines(text)
    if quote:
        items = [f"{quote}{i}{quote}" for i in items]
    return ', '.join(items)


def lines_to_sql_in(text, quote="'"):
    items = _split_lines(text)
    inner = ', '.join(f"{quote}{i}{quote}" for i in items)
    return f'({inner})'


def lines_to_sql_in_no_quotes(text):
    items = _split_lines(text)
    return '(' + ', '.join(items) + ')'


def lines_to_sql_in_double(text):
    return lines_to_sql_in(text, quote='"')


# ── Joined → lines ────────────────────────────────────────────────────────────

def csv_to_lines(text):
    return '\n'.join(_split_csv(text))


def space_to_lines(text):
    return '\n'.join(w for w in re.split(r'\s+', text.strip()) if w)


def sql_in_to_lines(text):
    text = text.strip().lstrip('(').rstrip(')')
    return csv_to_lines(text)


# ── Cleaning ──────────────────────────────────────────────────────────────────

def strip_quotes(text):
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
            s = s[1:-1]
        lines.append(s)
    return '\n'.join(lines)


def deduplicate(text):
    seen, result = set(), []
    for line in text.splitlines():
        if line not in seen:
            seen.add(line)
            result.append(line)
    return '\n'.join(result)


def sort_lines(text, reverse=False):
    return '\n'.join(sorted(text.splitlines(), reverse=reverse))


def trim_lines(text):
    return '\n'.join(l.strip() for l in text.splitlines())


# ── Registry ──────────────────────────────────────────────────────────────────
# Each entry: (display_name, fn, required_input_types)
# required_input_types: set of tags that must overlap with detected types.
# Empty set means the transform applies to any non-empty input.

TRANSFORMS = [
    # Beautify
    ('Beautify (JSON / SQL)',             beautify,                            {'json', 'sql'}),
    # JSON
    ('JSON → Object (pretty)',            json_to_object,                      {'json'}),
    ('JSON → values (one per line)',      json_to_values,                      {'json'}),
    ('JSON Stringify',                    json_stringify,                      set()),
    ('JSON Unstringify',                  json_unstringify,                    {'json_string'}),
    # Lines → CSV
    ('Lines → CSV (no quotes)',           lambda t: lines_to_csv(t, ''),       {'lines'}),
    ("Lines → CSV (' quoted)",            lambda t: lines_to_csv(t, "'"),      {'lines'}),
    ('Lines → CSV (" quoted)',            lambda t: lines_to_csv(t, '"'),      {'lines'}),
    # Lines → SQL
    ('Lines → SQL IN() (no quotes)',      lines_to_sql_in_no_quotes,           {'lines'}),
    ("Lines → SQL IN() (' quotes)",       lines_to_sql_in,                     {'lines'}),
    ('Lines → SQL IN() (" quotes)',       lines_to_sql_in_double,              {'lines'}),
    # SQL → Lines
    ('SQL IN() → Lines',                  sql_in_to_lines,                     {'sql_in'}),
    # Split
    ('CSV → Lines',                       csv_to_lines,                        {'csv'}),
    ('Words/spaces → Lines',              space_to_lines,                      {'words'}),
    # Clean
    ('Strip surrounding quotes',          strip_quotes,                        set()),
    ('Deduplicate lines',                 deduplicate,                         {'lines'}),
    ('Trim whitespace per line',          trim_lines,                          set()),
    # Sort
    ('Sort lines A → Z',                  sort_lines,                          {'lines'}),
    ('Sort lines Z → A',                  lambda t: sort_lines(t, reverse=True), {'lines'}),
    # Case
    ('UPPERCASE',                         str.upper,                           set()),
    ('lowercase',                         str.lower,                           set()),
    ('Title Case',                        str.title,                           set()),
]


def output_extension(text):
    """Return the best file extension for saving the given text."""
    text = text.strip()
    if _is_json_object(text):
        return 'json'
    if _is_sql(text):
        return 'sql'
    return 'txt'


def ordered_transforms():
    """Return TRANSFORMS sorted by user-defined order from settings."""
    import settings as S
    order = S.get().transform_order
    if not order:
        return list(enumerate(TRANSFORMS))
    name_to_idx = {name: i for i, (name, _, _) in enumerate(TRANSFORMS)}
    ordered = []
    seen = set()
    for name in order:
        if name in name_to_idx:
            i = name_to_idx[name]
            ordered.append((i, TRANSFORMS[i]))
            seen.add(i)
    for i, t in enumerate(TRANSFORMS):
        if i not in seen:
            ordered.append((i, t))
    return ordered


def applicable_transforms(text):
    """Return list of (index, name, fn) in user order, filtered by input type and hidden list."""
    import settings as S
    hidden = set(S.get().hidden_transforms)
    types = detect_input_type(text)
    result = []
    for i, (name, fn, required) in ordered_transforms():
        if not text.strip():
            continue
        if name in hidden:
            continue
        if not required or required & types:
            result.append((i, name, fn))
    return result
