# The PDFs' typeface: Inter

The four files here (`inter-400`, `-600`, `-700` and `-800.woff2`) are Inter 4.001 (name table: *Version 4.001;git-66647c0bb*), a Latin subset of 518 glyphs. They are copied byte for byte, unchanged, from the print fonts of the iVendNext brand kit (`_brand/fonts/`, internal, at commit `40c6dcbde`): a defect here is a defect there: report it through the feedback forms ([`feedback/README.md`](../../../feedback/README.md)), and we take it to the brand kit's owners. The original is https://github.com/rsms/inter. Licence: the SIL Open Font License 1.1, in [`OFL.txt`](OFL.txt).

The brand guidelines name one typeface for print, Inter. Only the PDFs use these files (`site/pdf/build_pdfs.py` embeds them); the site keeps its own font in `site/assets-src/fonts/`. The subset has no ☐, → or ≤: the PDFs draw tick boxes with borders and write *at most* in words, and a PDF that embeds any font not named Inter is refused.
