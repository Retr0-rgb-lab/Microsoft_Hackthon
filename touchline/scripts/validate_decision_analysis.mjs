import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const ajv=new Ajv2020({allErrors:true,strict:true,strictRequired:false,allowUnionTypes:true});addFormats(ajv);
for(const p of ['schema.json','contracts/schema.json','contracts/decision-analysis/schema.json'])ajv.addSchema(read(p));
const id='urn:nextplay:decision-analysis:1.0.0',schema=read('contracts/decision-analysis/schema.json');
for(const name of Object.keys(schema.$defs))ajv.getSchema(`${id}#/$defs/${name}`);
if(process.argv.includes('--stdin')){
 const chunks=[];for await(const chunk of process.stdin)chunks.push(chunk);
 for(const line of Buffer.concat(chunks).toString().split('\n').filter(Boolean)){
  const {schema:name,value}=JSON.parse(line),fn=ajv.getSchema(`${id}#/$defs/${name}`);if(!fn)throw Error('Unknown schema');
  const valid=fn(value);console.log(JSON.stringify({valid,errors:valid?[]:fn.errors}));
 }
}else{
 for(const name of Object.keys(schema.$defs)){
  const filename=path.join(root,'contracts/decision-analysis/examples',name+'.json');if(!fs.existsSync(filename))continue;
  const fn=ajv.getSchema(`${id}#/$defs/${name}`);if(!fn(JSON.parse(fs.readFileSync(filename))))throw Error(JSON.stringify(fn.errors));
 }
 console.log('Decision analysis extension Schema compilation/examples: PASS');
}
