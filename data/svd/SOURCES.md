# Vendored SVD sources & provenance

These CMSIS-SVD files are the Tier-1 ground truth for chipsage. They are vendored (committed)
so that tests and CI are hermetic and the loader never touches the network. Each file is
pinned by SHA-256; `scripts/fetch_svds.py` re-downloads and verifies against these hashes.

| File | Device | SVD `<version>` | Source |
|------|--------|-----------------|--------|
| `RP2040.svd` | RP2040 | 0.1 | raspberrypi/pico-sdk · `src/rp2040/hardware_regs/RP2040.svd` |
| `RP2350.svd` | RP2350 | 0.1 | raspberrypi/pico-sdk · `src/rp2350/hardware_regs/RP2350.svd` |

**Upstream URLs** (fetched from `master` on 2026-07-03; the SHA-256 below is the real pin):

- https://raw.githubusercontent.com/raspberrypi/pico-sdk/master/src/rp2040/hardware_regs/RP2040.svd
- https://raw.githubusercontent.com/raspberrypi/pico-sdk/master/src/rp2350/hardware_regs/RP2350.svd

**SHA-256**

```
1c72330127ae097c8c9a3661b509fcb9a94826d76a5c0d7e259eb605ddd7b0a6  RP2040.svd
e75578fbc6aee06ddf875fd2fe71d7ab59fc19fb406c7eed58849a6c8cf491fd  RP2350.svd
```

**Licence.** These files originate from the Raspberry Pi
[pico-sdk](https://github.com/raspberrypi/pico-sdk) and are distributed by Raspberry Pi Ltd
under **BSD-3-Clause** (see the SPDX header at the top of each file). They retain their
upstream licence; they are not covered by chipsage's own MIT licence.
