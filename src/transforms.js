// ClipKit text transforms + content-type detection.
// Usable in both the main process (require) and renderer (script tag → window.ClipKitTransforms).
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.ClipKitTransforms = api;
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  // ── helpers ──────────────────────────────────────────────────────────────
  function splitLines(text) {
    return text.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
  }

  function splitCsv(text) {
    return text.trim().split(/,\s*/).map(p => {
      p = p.trim();
      if (p.length >= 2 && p[0] === p[p.length - 1] && (p[0] === '"' || p[0] === "'")) {
        p = p.slice(1, -1);
      }
      return p;
    });
  }

  // Must start with a SQL keyword — prevents log lines / prose from matching
  const SQL_START = /^(SELECT|INSERT\s+INTO|INSERT|UPDATE|DELETE\s+FROM|DELETE|CREATE\s+(TABLE|INDEX|VIEW|DATABASE)|DROP\s+(TABLE|INDEX|VIEW|DATABASE)|ALTER\s+TABLE|TRUNCATE|WITH|EXPLAIN|GRANT|REVOKE)\b/i;
  const URL_RE = /^(https?:\/\/|www\.)[^\s]+$/i;

  function tryJsonParse(text) {
    try { return { ok: true, value: JSON.parse(text) }; }
    catch (e) { return { ok: false }; }
  }

  function isJsonObject(text) {
    const r = tryJsonParse(text.trim());
    return r.ok && (typeof r.value === 'object' && r.value !== null);
  }

  function isJsonString(text) {
    const t = text.trim();
    if (!(t.startsWith('"') && t.endsWith('"'))) return false;
    const r = tryJsonParse(t);
    return r.ok && typeof r.value === 'string';
  }

  function isSql(text) {
    const t = text.trim();
    // Multi-statement: check first non-empty, non-comment line
    const firstLine = t.split(/\r?\n/).find(l => l.trim() && !l.trim().startsWith('--'));
    return SQL_START.test((firstLine || t).trim());
  }

  // ── detection ────────────────────────────────────────────────────────────
  // Returns a Set of tags: json, json_string, sql, sql_in, csv, url, code, lines, words, any
  function detectType(text) {
    text = (text || '').trim();
    const types = new Set();
    if (!text) return types;
    types.add('any');

    const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
    const multiline = lines.length > 1;

    const jsonObj = isJsonObject(text);
    if (jsonObj) types.add('json');
    if (isJsonString(text)) types.add('json_string');
    if (isSql(text)) types.add('sql');

    if (multiline && !jsonObj && !types.has('sql')) types.add('lines');

    if (!multiline) {
      const single = text;
      if (single.includes(',')) types.add('csv');
      if (/^\(.*\)$/s.test(single) && single.includes(',')) types.add('sql_in');
      if (/\s/.test(single)) types.add('words');
      if (URL_RE.test(single)) types.add('url');
    }

    // code heuristic (for the history badge)
    if (!jsonObj && /[{};=]/.test(text) && /[(){}\[\];]/.test(text)) {
      types.add('code');
    }

    return types;
  }

  // Single primary badge label/key for a history row.
  function primaryType(text) {
    const t = detectType(text);
    if (t.has('json') || t.has('json_string')) return 'JSON';
    if (t.has('sql') || t.has('sql_in')) return 'SQL';
    if (t.has('csv')) return 'CSV';
    if (t.has('url')) return 'URL';
    if (t.has('code')) return 'Code';
    return 'Text';
  }

  // ── beautify ─────────────────────────────────────────────────────────────
  function beautify(text) {
    text = text.trim();
    if (isJsonObject(text)) {
      return JSON.stringify(JSON.parse(text), null, 2);
    }
    if (isSql(text)) {
      return formatSql(text);
    }
    return text;
  }

  // Lightweight SQL formatter (no external deps).
  function formatSql(sql) {
    const KW = ['SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'INSERT INTO', 'VALUES',
      'UPDATE', 'SET', 'DELETE FROM', 'CREATE TABLE', 'ALTER TABLE', 'DROP TABLE',
      'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'OUTER JOIN', 'JOIN', 'GROUP BY',
      'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET', 'ON', 'WITH', 'UNION'];
    // collapse whitespace
    let s = sql.replace(/\s+/g, ' ').trim();
    // upper-case keywords
    KW.forEach(kw => {
      const re = new RegExp('\\b' + kw.replace(/ /g, '\\s+') + '\\b', 'gi');
      s = s.replace(re, kw);
    });
    const NEWLINE_BEFORE = ['FROM', 'WHERE', 'AND', 'OR', 'INSERT INTO', 'VALUES',
      'UPDATE', 'SET', 'DELETE FROM', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN',
      'OUTER JOIN', 'JOIN', 'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET',
      'UNION'];
    NEWLINE_BEFORE.forEach(kw => {
      const re = new RegExp('\\s+' + kw.replace(/ /g, '\\s+') + '\\b', 'g');
      s = s.replace(re, '\n' + kw);
    });
    // indent AND/OR
    s = s.replace(/\n(AND|OR)\b/g, '\n  $1');
    return s.trim();
  }

  // ── JSON ─────────────────────────────────────────────────────────────────
  function jsonStringify(text) {
    return JSON.stringify(text);
  }

  function jsonUnstringify(text) {
    const t = text.trim();
    const r = tryJsonParse(t);
    if (!r.ok) throw new Error('Input is not a valid JSON string literal');
    if (typeof r.value === 'string') return r.value;
    return JSON.stringify(r.value, null, 2);
  }

  const IDENT = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

  function jsonToObject(text) {
    const r = tryJsonParse(text);
    if (!r.ok) throw new Error('Input is not valid JSON');

    function conv(obj, indent) {
      const pad = '    '.repeat(indent);
      const inner = '    '.repeat(indent + 1);
      if (Array.isArray(obj)) {
        if (obj.length === 0) return '[]';
        const lines = obj.map(v => inner + conv(v, indent + 1) + ',');
        return '[\n' + lines.join('\n') + '\n' + pad + ']';
      }
      if (obj !== null && typeof obj === 'object') {
        const keys = Object.keys(obj);
        if (keys.length === 0) return '{}';
        const lines = keys.map(k => {
          const key = IDENT.test(k) ? k : "'" + k + "'";
          return inner + key + ': ' + conv(obj[k], indent + 1) + ',';
        });
        return '{\n' + lines.join('\n') + '\n' + pad + '}';
      }
      if (obj === null) return 'null';
      if (typeof obj === 'boolean') return obj ? 'true' : 'false';
      if (typeof obj === 'number') return String(obj);
      const escaped = String(obj).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      return "'" + escaped + "'";
    }
    return conv(r.value, 0);
  }

  function jsonToValues(text) {
    const r = tryJsonParse(text);
    if (!r.ok) throw new Error('Input is not valid JSON');
    const seen = new Set();
    const result = [];
    function collect(node) {
      if (Array.isArray(node)) { node.forEach(collect); }
      else if (node !== null && typeof node === 'object') { Object.values(node).forEach(collect); }
      else {
        const s = String(node).trim();
        if (s && !seen.has(s)) { seen.add(s); result.push(s); }
      }
    }
    collect(r.value);
    return result.join('\n');
  }

  // ── lines → joined ──────────────────────────────────────────────────────
  function linesToCsv(text, quote) {
    let items = splitLines(text);
    if (quote) items = items.map(i => quote + i + quote);
    return items.join(', ');
  }

  function linesToSqlIn(text, quote) {
    const items = splitLines(text);
    const inner = items.map(i => quote + i + quote).join(', ');
    return '(' + inner + ')';
  }

  function linesToSqlInNoQuotes(text) {
    return '(' + splitLines(text).join(', ') + ')';
  }

  // ── joined → lines ──────────────────────────────────────────────────────
  function csvToLines(text) { return splitCsv(text).join('\n'); }

  function spaceToLines(text) {
    return text.trim().split(/\s+/).filter(w => w.length > 0).join('\n');
  }

  function sqlInToLines(text) {
    let t = text.trim().replace(/^\(/, '').replace(/\)$/, '');
    return csvToLines(t);
  }

  // ── cleaning ─────────────────────────────────────────────────────────────
  function stripQuotes(text) {
    return text.split(/\r?\n/).map(line => {
      let s = line.trim();
      if (s.length >= 2 && s[0] === s[s.length - 1] && (s[0] === '"' || s[0] === "'")) {
        s = s.slice(1, -1);
      }
      return s;
    }).join('\n');
  }

  function deduplicate(text) {
    const seen = new Set();
    const result = [];
    text.split(/\r?\n/).forEach(line => {
      if (!seen.has(line)) { seen.add(line); result.push(line); }
    });
    return result.join('\n');
  }

  function sortLines(text, reverse) {
    const arr = text.split(/\r?\n/).sort();
    if (reverse) arr.reverse();
    return arr.join('\n');
  }

  function trimLines(text) {
    return text.split(/\r?\n/).map(l => l.trim()).join('\n');
  }

  function titleCase(text) {
    return text.replace(/\w\S*/g, w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
  }

  // ── registry ─────────────────────────────────────────────────────────────
  // { name, fn, required: [tags] }  empty required → applies to any non-empty input.
  const TRANSFORMS = [
    { name: 'Beautify (JSON / SQL)', fn: beautify, required: ['json', 'sql'] },
    { name: 'JSON → Object (pretty)', fn: jsonToObject, required: ['json'] },
    { name: 'JSON → values (one per line)', fn: jsonToValues, required: ['json'] },
    { name: 'JSON Stringify', fn: jsonStringify, required: [] },
    { name: 'JSON Unstringify', fn: jsonUnstringify, required: ['json_string'] },
    { name: 'Lines → CSV (no quotes)', fn: t => linesToCsv(t, ''), required: ['lines'] },
    { name: "Lines → CSV (' quoted)", fn: t => linesToCsv(t, "'"), required: ['lines'] },
    { name: 'Lines → CSV (" quoted)', fn: t => linesToCsv(t, '"'), required: ['lines'] },
    { name: 'Lines → SQL IN() (no quotes)', fn: linesToSqlInNoQuotes, required: ['lines'] },
    { name: "Lines → SQL IN() (' quotes)", fn: t => linesToSqlIn(t, "'"), required: ['lines'] },
    { name: 'Lines → SQL IN() (" quotes)', fn: t => linesToSqlIn(t, '"'), required: ['lines'] },
    { name: 'SQL IN() → Lines', fn: sqlInToLines, required: ['sql_in'] },
    { name: 'CSV → Lines', fn: csvToLines, required: ['csv'] },
    { name: 'Words/spaces → Lines', fn: spaceToLines, required: ['words'] },
    { name: 'Strip surrounding quotes', fn: stripQuotes, required: [] },
    { name: 'Deduplicate lines', fn: deduplicate, required: ['lines'] },
    { name: 'Trim whitespace per line', fn: trimLines, required: [] },
    { name: 'Sort lines A → Z', fn: t => sortLines(t, false), required: ['lines'] },
    { name: 'Sort lines Z → A', fn: t => sortLines(t, true), required: ['lines'] },
    { name: 'UPPERCASE', fn: t => t.toUpperCase(), required: [] },
    { name: 'lowercase', fn: t => t.toLowerCase(), required: [] },
    { name: 'Title Case', fn: titleCase, required: [] }
  ];

  function transformByName(name) {
    return TRANSFORMS.find(t => t.name === name) || null;
  }

  // Returns TRANSFORMS in user order (from settings.transformOrder), unknowns appended.
  function orderedTransforms(order) {
    if (!order || order.length === 0) return TRANSFORMS.slice();
    const byName = {};
    TRANSFORMS.forEach(t => { byName[t.name] = t; });
    const out = [];
    const seen = new Set();
    order.forEach(n => { if (byName[n]) { out.push(byName[n]); seen.add(n); } });
    TRANSFORMS.forEach(t => { if (!seen.has(t.name)) out.push(t); });
    return out;
  }

  // Filtered + ordered list applicable to the given text.
  // Only shows type-specific transforms when the input has a known type.
  // Universal transforms (required:[]) only appear when nothing specific matches.
  function applicableTransforms(text, opts) {
    opts = opts || {};
    const hidden = new Set(opts.hidden || []);
    const types = detectType(text);
    const list = orderedTransforms(opts.order);
    if (!text || !text.trim()) return [];

    const specific = list.filter(t => {
      if (hidden.has(t.name)) return false;
      return t.required.length > 0 && t.required.some(r => types.has(r));
    });
    if (specific.length > 0) return specific;

    // No specific matches — fall back to universal transforms
    return list.filter(t => {
      if (hidden.has(t.name)) return false;
      return t.required.length === 0;
    });
  }

  function applyByName(name, text) {
    const t = transformByName(name);
    if (!t) throw new Error('Unknown transform: ' + name);
    return t.fn(text);
  }

  return {
    TRANSFORMS,
    detectType,
    primaryType,
    transformByName,
    orderedTransforms,
    applicableTransforms,
    applyByName
  };
});
