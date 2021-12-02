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

async function parseImJoyPlugin(source){
  let content = await (await fetch(source)).text();
    const parsed = /<config(.*?)>(.*?)<\/config>/gm.exec(content);
    const type = parsed[1];
    let item;
    if(type=="yaml"){
      item = yaml.load(parsed[2]);
    }
    else{
      item = JSON.parse(parsed[2]);
    }

      
    const app_config = {
      "id": item["id"],
      "type": "application",
      "source": source,
      "passive": item["passive"] || false,
    }
    fields = [
      "icon",
      "name",
      "version",
      "api_version",
      "description",
      "license",
      "requirements",
      "dependencies",
      "env",
      "passive",
    ]
    for(let f of fields){
      if(plugin_config.includes(f))
          app_config[f] = plugin_config[f]
    }
    tags = plugin_config.tags || []
    if(!tags.includes("bioengine"))
      tags.push("bioengine")
    app_config["tags"] = tags
      
    app_config["documentation"] = plugin_config.docs
    app_config["covers"] = plugin_config.cover
    // make sure we have a list
    if(!app_config["covers"]){
      app_config["covers"] = []
    }else if(typeof app_config["covers"] !== "object"){
      app_config["covers"] = [app_config["covers"]]
    }

    app_config["badges"] = plugin_config.badge
    if(!app_config["badges"]){
      app_config["badges"] = []
    }else if(typeof app_config["badges"] !== "object"){
      app_config["badges"] = [app_config["badges"]]
    }

    app_config["authors"] = plugin_config.author
    if(!app_config["authors"]){
      app_config["authors"] = []
    }else if(typeof app_config["authors"] !== "object"){
      app_config["authors"] = [app_config["authors"]]
    }

  return app_config
}
async function getResourceItemsFromPartner(source) {
  console.log("Getting resource items from " + source);
  const collection = yaml.load(await (await fetch(source)).text());
  const items = [];
  for(let type of ["dataset", "application"]) {
    if (collection[type]) {
      for(let item of collection[type]) {
        item.type = type;
        if(type === "application" && item.source && item.source.endsWith(".imjoy.html")){
          // item = await parseImJoyPlugin(item.source)
        }
        else
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
  const newRdfs = yaml.load(templateStr);
  const passedRdfs = yaml.load(templateStr); // copy template
  const partners = [{id: "zenodo"}].concat(passedRdfs.config.partners)
  // regroup the attachments as types
  passedRdfs.attachments = {};
  let newItemCount = 0;
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
      if(resources.config.id !== partner.id) {
        throw new Error("Partner id does not match source id");
      }
      for(let k of Object.keys(resources.config)) {
        partner[k] = resources.config[k];
      }
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
    newRdfs.attachments[partner.id] = newItems;
    newItemCount += newItems.length;
    passedItems.forEach(item => {
      passedRdfs.attachments[item.type] = passedRdfs.attachments[item.type] || [];
      passedRdfs.attachments[item.type].push(item);
    });
    newIndexRdf.attachments[partner.id] = items.map(item => {
      return { id: item.id, status: item.status, type: item.type };
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
    if(newItemCount >0){
      console.log(`Saving ${newItemCount} new items to test-rdf.yaml`)
      // test only the new items
      await writeFile("./dist/test-rdf.yaml", yaml.dump(newRdfs));
    }
    else{
      console.log(`No new items for testing, skip producing test-rdf.yaml`)
    }
  }
}

var args = process.argv.slice(2);
main(args);
