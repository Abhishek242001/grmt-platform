# Gudsky brand assets

Source: official Gudsky Research Foundation assets, www.gudsky.org — do not
substitute placeholder/unofficial artwork; request current files from GRF
if anything here is missing or looks outdated.

## Expected files (none present yet — drop them in here)

- `logo-full-color.svg`     — primary logo, full color, for light backgrounds
- `logo-white.svg`          — reversed/white logo, for dark backgrounds and footers
- `logo-mark-only.svg`      — icon/mark only, no wordmark — used as favicon source
- `favicon.ico`             — generated from logo-mark-only.svg
- `color-palette.md`        — hex values for primary/secondary/accent colors, pulled
                              from the official site's stylesheet, so the frontend
                              theme matches gudsky.org rather than an approximated color
- `letterhead-template.docx` — if GRF has an existing letterhead, for any generated
                              PDF/Word exports (e.g. analytics reports) that should
                              carry official branding

## Known source

The official site (https://www.gudsky.org) references a logo at
`/assets/images/logos/GudskyLOGO.jpg` — this is a raster (JPG) copy suitable for
reference only, not for production use (no transparency, not vector, not a
reversed/white variant). Request the source vector files and official color
palette directly from Gudsky Research Foundation rather than extracting them
from the raster logo or screenshots.

## Do not

- Commit low-resolution screenshots or watermarked social-media exports as the
  working logo files.
- Guess at brand colors from screenshots — use the frontend's neutral
  placeholder theme until `color-palette.md` above is populated with real values.
