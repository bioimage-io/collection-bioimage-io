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
  globalThis.localStorage = new LocalStorage("./scratch");
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
);

async function getResourceItemsFromPartner(source) {
  console.log("Getting resource items from " + source);
  const collection = yaml.load(await (await fetch(source)).text());
  const items = [];
  for(let type of ["dataset", "application"]) {
    if (collection[type]) {
      for(let item of collection[type]) {
        items.push(item);
      }
    }
  }
  return {config: collection.config, items: items};
}

async function main(args) {
  if (!fs.existsSync("./dist")) await mkdir("./dist");
  const templateStr = await readFile(indexRdf);
  const newIndexRdf = yaml.load(templateStr);
  const pendingRdfs = yaml.load(templateStr);
  const passedRdfs = yaml.load(templateStr); // copy template
  const partners = [{id: "zenodo"}].concat(passedRdfs.config.partners)
  for(let partner of partners) {
    let items;
    if (partner.id === "zenodo") {
      items = await zenodoClient.getResourceItems({
        community: null, // siteConfig.zenodo_config.community,
        size: 10000 // only show the first 10000 items
      });
    }
    else{
      const resources = await getResourceItemsFromPartner(partner.source);
      partner.config = resources.config;
      items = resources.items;
    }
    const currentItems = newIndexRdf.attachments[partner.id] || [];
    const newItems = [];
    items.forEach(item => {
      if (item.config && item.config._deposit) {
        delete item.config._deposit;
      }
      const matched = currentItems.find(i => i.id === item.id);
      if (!matched) {
        item.status = "pending";
        newItems.push(item);
      } else {
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
    });
    const passedItems = items.filter(item => item.status === "passed");
    const pendingItems = items.filter(item => item.status === "pending");
    console.log(
      "Passed rdf items in " + partner.id,
      passedItems.map(item => item.id)
    );
    console.log(
      "New rdf items in " + partner.id,
      newItems.map(item => item.id)
    );
    console.log(
      "Removed rdf items in " + partner.id,
      removedItems.map(item => item.id)
    );
    console.log(
      "Pending rdf items in " + partner.id,
      pendingItems.map(item => item.id)
    );
    pendingRdfs.attachments[partner.id] = pendingItems;
    passedRdfs.attachments[partner.id] = passedItems;
    newIndexRdf.attachments[partner.id] = items.map(item => {
      return { id: item.id, status: item.status };
    });
  }
  await writeFile("./dist/rdf.yaml", yaml.dump(passedRdfs));
  await writeFile("./dist/rdf.json", JSON.stringify(passedRdfs));
  if (args.includes("--overwrite")) { // for running on the main branch
    await writeFile("./rdf.yaml", yaml.dump(newIndexRdf));
    // test all items
    await writeFile("./dist/test-rdf.yaml", yaml.dump(passedRdfs));
  } else { // for the PR
    await writeFile("./new-rdf.yaml", yaml.dump(newIndexRdf));
    // test only the new items
    await writeFile("./dist/test-rdf.yaml", yaml.dump(pendingRdfs));
  }
}

var args = process.argv.slice(2);
main(args);
