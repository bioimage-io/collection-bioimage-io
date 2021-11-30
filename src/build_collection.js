import { ZenodoClient } from "./utils.js";
import siteConfig from "./site.config.json";
import fetch from "node-fetch";
import { readFile, writeFile, mkdir, copyFile } from "fs/promises";
import { LocalStorage } from "node-localstorage";
import fs from "fs";

import yaml from "js-yaml";

const indexRdf = "./rdf.yaml";

if (!globalThis.fetch) {
  globalThis.fetch = fetch;
}

if (!globalThis.localStorage) {
  globalThis.localStorage = new LocalStorage('./scratch');
}

const zenodoBaseURL = siteConfig.zenodo_config.use_sandbox
  ? "https://sandbox.zenodo.org"
  : "https://zenodo.org";

const client_id = siteConfig.zenodo_config.use_sandbox
  ? siteConfig.zenodo_config.sandbox_client_id
  : siteConfig.zenodo_config.production_client_id;

const zenodoClient = new ZenodoClient(
  zenodoBaseURL,
  client_id,
  siteConfig.zenodo_config.use_sandbox
)

async function main(args) {
  if (!fs.existsSync("./dist")) await mkdir("./dist");
  const templateStr = await readFile(indexRdf);
  const newIndexRdf = yaml.load(templateStr);
  const generated = yaml.load(templateStr); // copy template
  const items = await zenodoClient.getResourceItems({
    community: siteConfig.zenodo_config.community,
    size: 10000, // only show the first 10000 items
  });
  const currentItems = newIndexRdf.attachments.zenodo;
  const newItems = [];
  items.forEach(item => {
    if (item.config._deposit) {
      delete item.config._deposit;
    }
    const matched = currentItems.find(i => i.id === item.id);
    if (!matched) {
      item.status = "pending";
      newItems.push(item);
    }
    else{
      item.status = matched.status;
    }
  });
  const removedItems = [];
  currentItems.forEach(item => {
    const matched = items.find(i => i.id === item.id);
    if (!matched) {
      item.status = "deleted";
      removedItems.push(item);
    }
  })
  const passedItems = items.filter(item => item.status === "passed");
  console.log("Passed rdf items", passedItems.map(item => item.id));
  console.log("New rdf items", newItems.map(item => item.id));
  console.log("Removed rdf items", removedItems.map(item => item.id));
  generated.attachments.zenodo = passedItems;
  newIndexRdf.attachments.zenodo = items.map(item => {return {"id": item.id, "status": item.status} })
  await writeFile("./dist/rdf.yaml", yaml.dump(generated));
  await writeFile("./dist/rdf.json", JSON.stringify(generated));
  if(newItems.length > 0 || removedItems.length > 0){
    if(args.includes("--overwrite")){
      await writeFile("./rdf.yaml", yaml.dump(newIndexRdf));
    }
    else{
      await writeFile("./new-rdf.yaml", yaml.dump(newIndexRdf));
    }
    await writeFile("./dist/new-rdf.yaml", yaml.dump(newItems));
    await writeFile("./dist/new-rdf.json", JSON.stringify(newItems));
  }
  else{
    console.log("No new items detected!");
  }
}

var args = process.argv.slice(2);
main(args);
