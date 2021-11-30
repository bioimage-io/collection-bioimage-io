const download = require("download");

download(
  "https://raw.githubusercontent.com/bioimage-io/bioimage.io/main/site.config.json",
  "scripts"
);
download(
  "https://raw.githubusercontent.com/bioimage-io/bioimage.io/main/src/utils.js",
  "scripts"
);
