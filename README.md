# bioimage.io RDF collections

# Partner Contributions

## Contribute resource test summaries
To contribute test summaries from one of your GitHub repositories we need to add an entry to [trigger_partner_wf.yaml](https://github.com/bioimage-io/collection-bioimage-io/blob/main/.github/workflows/trigger_partner_wf.yaml#L21-L26), which will trigger a suitable workflow in your repository, e.g.
for ilastik: https://github.com/ilastik/bioimage-io-resources/actions/workflows/test_bioimageio_resources.yaml.
In the partner section of [collection_rdf_template.yaml](https://github.com/FynnBe/collection-bioimage-io/blob/main/collection_rdf_template.yaml)
we need to specify your partner_id (e.g. 'ilastik') and your workflow deploys your test summaries.

# Uploading models via bioimage.io

Go to https://bioimage.io/#/, press the `Upload` button, log in to zenodo, authorize bioimage.io, select the model to be uploaded and upload it.
See the video below for a step-by-step example. Make sure to enter your correct github name in the `Maintainer` field so that you get notified in the next step.

https://user-images.githubusercontent.com/4263537/156735114-b322c341-8588-47f0-a271-3e292418785b.mp4

Once the upload has succeeded your model will be deposited on zenodo. It will not be available on bioimage.io yet. For this, it still needs to be registered with [collection-bioimagei-io](https://github.com/bioimage-io/collection-bioimage-io). A pull request for this will be opened automatically and you will be tagged in it (if you have entered your correct github user name earlier). The PR will look something like this:

![upload-pr-tests-running](https://user-images.githubusercontent.com/4263537/156736230-f4abddaa-4e89-4b32-982e-983e59e8fd74.png)

This PR will be automatically checked and a bioimage.io team member will merge it if all checks passed and all other quality standards are met.
