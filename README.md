# BioImage.IO RDF collections

# Partner Contributions
## Contribute resource test summaries
To contribute test summaries from one of your GitHub repositories we need to add an entry to [trigger_partner_wf.yaml](https://github.com/bioimage-io/collection-bioimage-io/blob/main/.github/workflows/trigger_partner_wf.yaml#L21-L26), which will trigger a suitable workflow in your repository, e.g.
for ilastik: https://github.com/ilastik/bioimage-io-resources/actions/workflows/test_bioimageio_resources.yaml.
In the partner section of [collection_rdf_template.yaml](https://github.com/FynnBe/collection-bioimage-io/blob/main/collection_rdf_template.yaml) 
we need to specify your partner_id (e.g. 'ilastik') and your workflow deploys your test summaries.
