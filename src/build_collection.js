import { ZenodoClient } from "./utils.js";
import siteConfig from "./site.config.json";
import fetch from "node-fetch";
import { readFile, writeFile, mkdir, copyFile } from "fs/promises";
import { LocalStorage } from "node-localstorage";
import fs from "fs";

import yaml from "js-yaml";


if (!globalThis.fetch) {
  globalThis.fetch = fetch;
}

if (!globalThis.localStorage) {
  globalThis.localStorage = new LocalStorage('./scratch');
}

const zenodoBaseURL = siteConfig.zenodo_config.use_sandbox
  ? "https://sandbox.zenodo.org"
  : "https://zenodo.org";

const zenodoClient = new ZenodoClient(
  zenodoBaseURL,
  siteConfig.zenodo_config.client_id,
  siteConfig.zenodo_config.use_sandbox
);

async function main() {
  if (!fs.existsSync("./dist")) await mkdir("./dist");
  const templateStr = await readFile("./rdf.yaml");
  const template = yaml.load(templateStr);
  const items = await zenodoClient.getResourceItems({
    community: siteConfig.zenodo_config.community,
    size: 10000, // only show the first 10000 items
  });
  items.forEach(item => {
    if (item.config._deposit) {
      delete item.config._deposit;
    }
  });
  console.log("All rdf items", items);
  template.attachments.zenodo = items;
  await writeFile("./dist/rdf.yaml", yaml.dump(template));
  await writeFile("./dist/rdf.json", JSON.stringify(template));
}

main();
