import { readFile } from "fs/promises";
import yaml from "js-yaml";

const indexRdf = "./rdf.yaml";

async function main() {
  const templateStr = await readFile(indexRdf);
  const newIndexRdf = yaml.load(templateStr);
  let currentItems = [];
  for(let category of Object.keys(newIndexRdf.attachments)) {
    currentItems = currentItems.concat(newIndexRdf.attachments[category]);
  }
  const passedItems = currentItems.filter(item => item.status === "passed");
  const pendingItems = currentItems.filter(item => item.status === "pending");
  console.log(
    "Passed rdf items",
    passedItems.map(item => item.id)
  );
  if(pendingItems.length > 0) {
    console.log(
      "ERROR: There are still pending rdf items: ",
      pendingItems.map(item => item.id)
    );
    console.log("Please resolve all the pending items in the rdf.yaml!!!")
    // Fail the test
    process.exit(1);
  }
  else{
    console.log("No pending rdf items");
  }
}
main();
