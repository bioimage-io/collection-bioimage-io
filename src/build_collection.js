import { ZenodoClient } from "./utils.js";
import siteConfig from "./site.config.json";
import fetch  from 'node-fetch';
import { readFile, writeFile, mkdir } from 'fs/promises';
import fs from "fs";

import yaml from "js-yaml";

if (!globalThis.fetch) {
	globalThis.fetch = fetch;
}


const zenodoBaseURL = siteConfig.zenodo_config.use_sandbox
  ? "https://sandbox.zenodo.org"
  : "https://zenodo.org";

const zenodoClient = new ZenodoClient(
    zenodoBaseURL,
    siteConfig.zenodo_config.client_id,
    siteConfig.zenodo_config.use_sandbox
  )

async function main(){
    if(!fs.existsSync("./dist"))
    await mkdir('./dist')
    const templateStr = await readFile("./rdf.yaml")
    const template = yaml.load(templateStr)
    const items = await zenodoClient.getResourceItems({
        community: siteConfig.zenodo_config.community
    });
    items.forEach((item)=>{
        if(item.config._deposit){
            delete item.config._deposit
        }
    })
    console.log("All rdf items", items);
    if(template.attachments.rdfs){
        template.attachments.rdfs = items.concat(template.attachments.rdfs)
    }
    else{
        template.attachments.rdfs = items;
    }
    await writeFile('./dist/rdf.yaml', yaml.dump(template))
    await writeFile('./dist/rdf.json', JSON.stringify(template))
}

main();
