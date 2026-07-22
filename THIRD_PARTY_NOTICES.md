# Third-party notices

This file covers the vendored font binaries and test-only axe-core asset. Python
package licenses remain available in their installed distributions and upstream
projects. It is not a license grant for this repository's original source code.

## Inter

- Asset: `static/fonts/InterVariable.woff2`
- Upstream: <https://github.com/rsms/inter>
- Version: `v4.1` (`e3a3d4c57d5ecc01453a575621882a384c1995a3`)
- SHA-256: `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3`
- License: SIL Open Font License 1.1; the unmodified upstream notice is in
  `third_party/fonts/inter/OFL.txt`.

## Source Serif 4

- Asset: `static/fonts/SourceSerif4Variable-Roman.woff2`
- Upstream: <https://github.com/adobe-fonts/source-serif>
- Release commit: `5f220b17d27ed64873f22cde0dd593685387bd19`
- SHA-256: `f146ee102dddcc5bc7a2cf4af5bcf129832195941b92bd0a512626f390688c1e`
- License: SIL Open Font License 1.1; the unmodified upstream notice is in
  `third_party/fonts/source-serif/LICENSE.md`.

## axe-core (test-only)

- Asset: `tests/vendor/axe.min.js`
- Upstream: <https://github.com/dequelabs/axe-core>
- Version: `v4.10.3`
- SHA-256: `880970c081707360e64f34cea25ff91892f5bc95675b0776925b9709dd8a68bb`
- Purpose: automated WCAG checks in the Playwright suite; it is not shipped in
  the production image.
- License: Mozilla Public License 2.0; the unmodified upstream notice is in
  `third_party/testing/axe-core/LICENSE`.
