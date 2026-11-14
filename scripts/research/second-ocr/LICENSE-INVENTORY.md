# Isolated second-OCR research: license and dependency inventory

Date: 2026-11-14. Research only; production remains disabled. This is an evidence inventory, **not a complete SBOM, CVE/security audit, legal clearance, or production deployment approval**. No production code is changed by this document.

## Evidence and scope

The referenced `signature-status.txt`, extracted copyright files and `ldd.txt` were inspected in the original local research environment and are not included in this source-only publication. Their recorded hashes and findings are historical evidence, not files readers should expect in this checkout. Re-extraction recreates package notices; a new container must produce its own dependency/signature evidence.

Reviewed `selected-packages.json`, extracted `root/usr/share/doc/*/copyright`, and the saved `ldd.txt` snapshot. The selected packages were downloaded from the Debian archive and locally extracted, not installed into the operating system. Signature verification is recorded separately in `signature-status.txt`; archive identity checks below independently compare the downloaded bytes with the selected Packages SHA256 values. Such checks establish identity, not vulnerability clearance.

## Selected Debian packages

| Package | Version | Architecture | Copyright classification | Archive SHA256 matches manifest |
|---|---|---|---|---|
| libicu72 | 72.1-3+deb12u1 | amd64 | Debian copyright: MIT for Files: *; GPL-3 for debian/* (different scopes) | True |
| liblept5 | 1.82.0-3+b3 | amd64 | BSD-style two-condition license; preserve exact bundled notice | True |
| libtesseract5 | 5.3.0-2 | amd64 | Apache-2.0 (upstream and Debian packaging) | True |
| tesseract-ocr | 5.3.0-2 | amd64 | Apache-2.0 (upstream and Debian packaging) | True |
| tesseract-ocr-eng | 1:4.1.0-2 | all | Apache-2.0; upstream tessdata_fast | True |

The exact package archive hashes, filenames and dependency expressions remain in `selected-packages.json`. Preserve the full extracted copyright files and applicable license texts if distributing artifacts; this summary does not replace them. ICU packaging GPL-3 scope must not be silently omitted, nor described as a finding that every ICU runtime file is GPL-3. Review actual redistributed contents and any notices/source obligations before release.

### Copyright evidence hashes

- `root/usr/share/doc/libicu72/copyright`: SHA256 `5bbff5f646ce750ac0a347e7f91793279b7422a1119820b5f75d98879c201c68`.
- `root/usr/share/doc/liblept5/copyright`: SHA256 `cff4f0cb5db14528a8b84f4a3389012d5c6e0f5a75a882509367b2147c05a83e`.
- `root/usr/share/doc/libtesseract5/copyright`: SHA256 `6970bc4b54eea0b95aa1bdddc713e6c568ccfc527857739d6bb9056faa85ab9c`.
- `root/usr/share/doc/tesseract-ocr/copyright`: SHA256 `6970bc4b54eea0b95aa1bdddc713e6c568ccfc527857739d6bb9056faa85ab9c`.
- `root/usr/share/doc/tesseract-ocr-eng/copyright`: SHA256 `33fb8161898e34fcf5c6b8585d6be97642d7e8f34a922e783c6c5c970d0b09ad`.

Primary public references: [Debian CLI package](https://packages.debian.org/bookworm/tesseract-ocr), [English model package](https://packages.debian.org/bookworm/tesseract-ocr-eng), [CLI/library copyright](https://metadata.ftp-master.debian.org/changelogs/main/t/tesseract/tesseract_5.3.0-2_copyright), [English model copyright](https://metadata.ftp-master.debian.org/changelogs/main/t/tesseract-lang/tesseract-lang_4.1.0-2_copyright). Exact local extracted notices are the version-specific evidence for this inventory.

## Declared package dependencies versus observed loading

These are separate claims. Packages Depends records installation requirements; ldd records this executable’s resolved startup shared-library graph on this host. Neither alone is a complete runtime/file inventory.

- **libicu72** Depends: `libc6 (>= 2.34), libgcc-s1 (>= 3.0), libstdc++6 (>= 12)`.
- **liblept5** Depends: `libc6 (>= 2.33), libgif7 (>= 5.1), libjpeg62-turbo (>= 1.3.1), libopenjp2-7 (>= 2.0.0), libpng16-16 (>= 1.6.2-1), libtiff6 (>= 4.0.3), libwebp7, libwebpmux3, zlib1g (>= 1:1.1.4)`.
- **libtesseract5** Depends: `libarchive13 (>= 3.0.4), libc6 (>= 2.34), libcurl4 (>= 7.16.2), libgcc-s1 (>= 3.0), libgomp1 (>= 4.9), liblept5 (>= 1.75.3), libstdc++6 (>= 11)`.
- **tesseract-ocr** Depends: `libarchive13 (>= 3.2.1), libc6 (>= 2.34), libcairo2 (>= 1.2.4), libcurl4 (>= 7.16.2), libfontconfig1 (>= 2.12.6), libgcc-s1 (>= 3.0), libglib2.0-0 (>= 2.12.0), libharfbuzz0b (>= 1.2.6), libicu72 (>= 72.1~rc-1~), liblept5 (>= 1.75.3), libpango-1.0-0 (>= 1.44.3), libpangocairo-1.0-0 (>= 1.22.0), libstdc++6 (>= 11), libtesseract5 (= 5.3.0-2), tesseract-ocr-eng (>= 4.0.9~), tesseract-ocr-osd (>= 4.0.9~)`.
- **tesseract-ocr-eng** Depends: `(none recorded)`.

The CLI package declares `tesseract-ocr-osd`, but it is **not among the five extracted packages**. This research uses fixed `--psm 10 --oem 1 -l eng`, not orientation detection; successful execution does not establish a complete Debian package installation.

In the saved ldd snapshot, only `libtesseract.so.5` and `liblept.so.5` resolve into the extracted research root. ICU72 is extracted but **not shown as loaded in this snapshot**. Do not equate downloaded packages with loaded libraries. Cairo/Pango and other declared CLI dependencies likewise are not all visible in this saved graph.

### Host-resolved libraries in saved ldd.txt

These resolve outside the extracted root, under host `/lib/x86_64-linux-gnu`. Their package versions, hashes, complete license texts and source obligations have **not** been inventoried here. A local dpkg-query ownership attempt did not resolve these saved paths; no host package version is inferred from a SONAME.

- `libarchive.so.13`
- `libcurl.so.4`
- `libstdc++.so.6`
- `libm.so.6`
- `libgcc_s.so.1`
- `libc.so.6`
- `libgomp.so.1`
- `libpng16.so.16`
- `libjpeg.so.62`
- `libgif.so.7`
- `libtiff.so.6`
- `libwebpmux.so.3`
- `libwebp.so.7`
- `libopenjp2.so.7`
- `libz.so.1`
- `libnettle.so.8`
- `libacl.so.1`
- `liblzma.so.5`
- `libzstd.so.1`
- `liblz4.so.1`
- `libbz2.so.1.0`
- `libxml2.so.2`
- `libnghttp3.so.9`
- `libnghttp2.so.14`
- `libidn2.so.0`
- `librtmp.so.1`
- `libssh2.so.1`
- `libpsl.so.5`
- `libssl.so.3`
- `libcrypto.so.3`
- `libgssapi_krb5.so.2`
- `libldap.so.2`
- `liblber.so.2`
- `libbrotlidec.so.1`
- `libLerc.so.4`
- `libjbig.so.0`
- `libdeflate.so.0`
- `libsharpyuv.so.0`
- `libxxhash.so.0`
- `libunistring.so.5`
- `libgnutls.so.30`
- `libhogweed.so.6`
- `libgmp.so.10`
- `libkrb5.so.3`
- `libk5crypto.so.3`
- `libcom_err.so.2`
- `libkrb5support.so.0`
- `libsasl2.so.2`
- `libbrotlicommon.so.1`
- `libp11-kit.so.0`
- `libtasn1.so.6`
- `libkeyutils.so.1`
- `libresolv.so.2`
- `libffi.so.8`

The host dynamic loader `/lib64/ld-linux-x86-64.so.2` and kernel-provided linux-vdso are also shown. ldd does not inventory later dlopen modules, operating-system data, Python/OpenCV/NumPy dependencies, fonts, or every file read. The English traineddata is a runtime data dependency, not an ldd entry.

## Outstanding release gates

- Build and test in the actual pinned Bookworm production image; current execution mixes extracted Bookworm components with host libraries. No full container validation is established.
- Produce an image-specific complete dependency inventory: resolved package versions, binary/model hashes, runtime data and all redistribution notices, including host/transitive components.
- Review license obligations for the actual distributed image and source availability where applicable. The five-package license summary cannot be propagated to all linked libraries.
- Run a separate current vulnerability/security review; signature/hash success is not a CVE audit.
- Confirm immutable engine/model/config ownership, per-job budgets, concurrent-job isolation, temporary-file cleanup and failure fallback before considering optional production enablement.
- Keep engine absence, invalid output, disagreement, resource limits and timeouts fail-closed to the original empty cell; no automatic downloads or inferred sequential digits.
- Validate broader real scanned documents and adversarial cases. The three rendered public-document simulations and one restored digit do not prove general accuracy.

## Conclusion

The selected package identities and their bundled copyright classifications are documented. The environment is intentionally a partial, host-dependent research setup. This inventory does not approve production enablement or claim complete licensing/security clearance.
