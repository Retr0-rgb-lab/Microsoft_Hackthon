#!/usr/bin/env python3
"""Optional: validate every record of a match directory against schema.json (needs `pip install jsonschema`)."""
import json, sys
from pathlib import Path
import jsonschema
S = json.load(open(Path(__file__).parent / 'schema.json'))
R = jsonschema.Draft202012Validator
R.check_schema(S)
root = Path(sys.argv[1])
def V(name):
    s = dict(S); s.pop('oneOf'); s['$ref'] = '#/$defs/' + name; return R(s)
V('metadata').validate(json.load(open(root / 'metadata.json')))
for name, f in (('tracking', 'tracking.jsonl'), ('event', 'events.jsonl'), ('state', 'states.jsonl')):
    v = V(name); n = 0
    for line in open(root / f):
        v.validate(json.loads(line)); n += 1
    print(name, 'ok', n)
