# First migration step

The existing SKRF.py entry point and cache are unchanged.
The new id_platform package uses only the Python standard library.
It is not yet connected to the Flet UI.

## Check

Run from the repository root:

```sh
python -m unittest discover -s tests -v
```

## Catalog contract

load_catalog(directory) recursively reads manifest.json files.
Required strings: id, version, title, status.
Status: draft, review, approved.
fields is a nonempty list of objects with unique name, dotted source,
and optional boolean required.
Approved manifests require nonempty sources with document, edition, location.
These checks verify metadata structure, not legal applicability or authenticity.
Only approved templates are returned by default. All versions remain separate.

## Prefill

prefill(template, context) returns copied values, provenance and missing fields.
Missing data never erases recognized data and is not fabricated.
Zero and False are valid values. A draft cannot be released.
release_allowed is a technical completeness flag, not approval, signature,
or proof of regulatory compliance. Callers must separately check applicability.

## Next steps

1. Verify normative sources and the first AOSR form.
2. Add reviewed manifests and controlled printable templates.
3. Add project storage, document snapshots and version history.
4. Integrate a document wizard into Flet without removing requirements search.
5. Add DOCX rendering and test output formatting.

No normative forms, signed documents or complete regulatory catalog are
claimed to be delivered by this first commit.
