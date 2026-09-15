# Individual project documents

Sources for the three deliverables of the NOVA 2026 individual project on plot 167.

| file | what it is |
|---|---|
| `proposal.md` | research questions and methods, the first submission |
| `report.md` | the written report, with results |
| `slides.md` | the 20 minute presentation, 15 slides |
| `FINDINGS.md` | running log of every finding, with what each does not settle |
| `figures/` | all eight figures |

## Building

The PDFs are generated and are not committed, in keeping with the rest of this
repository. Rebuild them with pandoc and weasyprint:

    pandoc report.md   -o report.pdf --pdf-engine=weasyprint --css=proposal.css \
        --standalone --mathml --embed-resources --resource-path=.
    pandoc proposal.md -o proposal.pdf --pdf-engine=weasyprint --css=proposal.css \
        --standalone --mathml --embed-resources --resource-path=.
    pandoc slides.md   -o slides.pdf --pdf-engine=weasyprint --css=slides.css \
        --standalone --section-divs --embed-resources --resource-path=. \
        --metadata title="NOVA 2026 individual project"

`slides.md` also converts to an editable deck with
`pandoc slides.md -o slides.pptx --slide-level=2 --resource-path=.`

`--section-divs` wraps every `h3` in a nested `<section>`, so `slides.css` scopes the
page break to `section.level2` only. Without that, any slide with a subheading splits
across two pages.

## Figures

`figures/` is committed although the figures are generated, because regenerating them
needs the 9.6 GB of point clouds that are deliberately not in version control. They are
the durable visual record of the analysis. `scripts/project/` reproduces the numbers;
the figure rendering lives with the analysis that produced each one.

## House style

No em dashes, no section symbol. Check before submitting:

    grep -c '—' *.md        # must be 0
