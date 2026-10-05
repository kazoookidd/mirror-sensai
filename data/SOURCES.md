# Sources of the documents in `data/docs/`

All documents are real, public French documents, reused under the
[Licence Ouverte / Open Licence 2.0 (Etalab)](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).
This file lives outside `data/docs/` on purpose, so the RAG does not ingest it.

## Company agreement (ACCO open data, DILA)

Collective company agreements are published by the French administration
(Direction de l'information légale et administrative) with personal names
replaced by "XXX".

| File | Agreement | Company | Signed | Source |
|---|---|---|---|---|
| `syd_accord_nao_2026.pdf` | Accord relatif à la négociation annuelle obligatoire au sein de l'UES SYD | SYD Groupe Digital Care (UES SYD), IDCC 1486 (Syntec) | 2026-07-23 | [ACCOTEXT000054863093](https://www.legifrance.gouv.fr/acco/id/ACCOTEXT000054863093) |

Downloaded on 2026-10-05 from the DILA open data archive
`https://echanges.dila.gouv.fr/OPENDATA/ACCO/ACCO_20260921-064627.tar.gz`
(original file `T04426061315-82282032000023.docx`), converted from Word to PDF
with LibreOffice. Content not modified.

## Labour law sheets (Service-Public.gouv.fr, DILA)

Each `loi_*.md` file starts with its own source line (sheet number, URL, check
date). Converted from the HTML page to Markdown; only site interface elements
(buttons, simulators) were removed.

| File | Sheet |
|---|---|
| `loi_teletravail.md` | [F13851](https://www.service-public.gouv.fr/particuliers/vosdroits/F13851) Télétravail du salarié dans le secteur privé |
| `loi_conges_payes.md` | [F2258](https://www.service-public.gouv.fr/particuliers/vosdroits/F2258) Congés payés du salarié dans le secteur privé |
| `loi_conge_mariage_pacs.md` | [F34154](https://www.service-public.gouv.fr/particuliers/vosdroits/F34154) Congé du salarié pour mariage ou Pacs |
| `loi_conge_deces.md` | [F2278](https://www.service-public.gouv.fr/particuliers/vosdroits/F2278) Congé pour le décès d'un membre de la famille |
| `loi_complementaire_sante.md` | [F20739](https://www.service-public.gouv.fr/particuliers/vosdroits/F20739) Complémentaire santé d'entreprise |
| `loi_reglement_interieur.md` | [F1905](https://www.service-public.gouv.fr/particuliers/vosdroits/F1905) Règlement intérieur d'une entreprise |

Downloaded on 2026-10-05.
