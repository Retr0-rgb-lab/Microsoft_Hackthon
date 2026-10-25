import json
import shutil
import subprocess
import unittest
from pathlib import Path
from decision.outcome import compare

ROOT=Path(__file__).resolve().parents[1]

class BrowserPortTests(unittest.TestCase):
    def test_browser_and_python_scores_match(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node required for browser/Python cross-check')
        bundle=json.loads((ROOT/'public-demo/data.json').read_text())
        fixtures=[]
        for match in bundle['matches'][:12]:
            for c in match['cases'][:3]:
                fixtures.append({'frame':c['record']['snapshot'],'metadata':match['metadata'],
                                 'expected':compare(c['record']['snapshot'],match['metadata'])})
        script="""import fs from 'node:fs';import assert from 'node:assert/strict';
import {compare} from './public-demo/inference.js';
const model=JSON.parse(fs.readFileSync('public-demo/value-model.json')),rates=JSON.parse(fs.readFileSync('public-demo/rates.json'));
for(const f of JSON.parse(fs.readFileSync(0,'utf8'))){const got=compare(f.frame,f.metadata,model,rates);const byId=new Map(got.candidates.map(c=>[c.action_id,c]));assert.equal(got.candidates.length,f.expected.candidates.length);for(const e of f.expected.candidates){const a=byId.get(e.action_id);assert(a);assert.equal(a.eligible,e.eligible);assert(Math.abs(a.value_gain-e.value_gain)<1e-10);}}"""
        subprocess.run([node,'--input-type=module','-e',script],cwd=ROOT,input=json.dumps(fixtures),text=True,check=True,capture_output=True)
