import { readFile } from "fs/promises";
import fs from "fs";
import yaml from "js-yaml";

async function main() {
  const currentItems = [];
  fs.readdirSync("collection").forEach(folder => {
    // if folder is a folder
    if (fs.lstatSync(`collection/${folder}`).isDirectory()) {
      fs.readdirSync(`collection/${folder}`).forEach(subfolder => {
        if (fs.lstatSync(`collection/${folder}/${subfolder}`).isDirectory()) {
          if (fs.existsSync(`collection/${folder}/${subfolder}/rdf.yaml`)) {
            const item = yaml.load(
              fs.readFileSync(`collection/${folder}/${subfolder}/rdf.yaml`)
            );
            currentItems.push(item);
          }
        }
      });
    }
  });
  const passedItems = currentItems.filter(
    item => item.config && item.config.status === "passed"
  );
  const pendingItems = currentItems.filter(
    item => item.config && item.config.status === "pending"
  );
  console.log(
    "Passed rdf items",
    passedItems.map(item => item.id)
  );
  if (pendingItems.length > 0) {
    console.log(
      "ERROR: There are still pending rdf items: ",
      pendingItems.map(item => item.id)
    );
    console.log("Please resolve all the pending items in the rdf.yaml!!!");
    // Fail the test
    process.exit(1);
  } else {
    console.log("No pending rdf items");
  }
}
main();
