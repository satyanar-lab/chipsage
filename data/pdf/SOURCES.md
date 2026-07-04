# Vendored datasheet sources & provenance

These datasheet PDFs are the **Tier-3** ground truth for chipsage (page-anchored prose and
errata). They are vendored (committed) unmodified so that tests and CI are hermetic and the
indexer never touches the network. Each file is pinned by SHA-256; `scripts/fetch_pdfs.py`
re-downloads and verifies against these hashes.

| File | Device | Pages | Build date | Source |
|------|--------|-------|------------|--------|
| `rp2040-datasheet.pdf` | RP2040 | 642 | 2025-02-20 | datasheets.raspberrypi.com |
| `rp2350-datasheet.pdf` | RP2350 | 1380 | 2025-07-29 | datasheets.raspberrypi.com |

**Upstream URLs** (fetched 2026-07-03; the SHA-256 below is the real pin):

- https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf
- https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf

**SHA-256**

```
be56fbb75ba0ae9e26558a73c93ac3e75c2ad4e6878d3b6703de2a76d886ea8c  rp2040-datasheet.pdf
2877d0f270fb6d6a57943bee58aaad536aa027bea1e5b1c4ce2541a3230d4be8  rp2350-datasheet.pdf
```

**Licence.** © 2020–2025 Raspberry Pi Ltd. The datasheets state, on page 2:

> This documentation is licensed under a Creative Commons Attribution-NoDerivatives 4.0
> International (CC BY-ND).

The files here are the **unmodified** originals — CC BY-ND permits redistributing the
verbatim work with attribution; it forbids distributing *derivatives*. chipsage does not
create or distribute a derivative datasheet: at build time it extracts text into a local
search index, and at query time its tools return short **verbatim, attributed excerpts with
page citations** (never paraphrased). They retain their Raspberry Pi licence and are not
covered by chipsage's own MIT licence. (Portions © Synopsys, Inc. and Arm Limited, as noted
in the datasheets.)
