# Frequently asked questions

[简体中文](常见问题.md) | **English**

## Does it automatically match the original font?

Yes. It first reuses the embedded font and searches for a complete copy of the same face if characters are missing. Similar-looking fonts are not silently substituted. Different releases of the same font family can differ, so review the result before printing.

## Why am I still getting a missing-character message?

A PDF may embed only characters used in its original text. If a complete matching font is unavailable, or the font never supported the new characters, supply the original font file or install it and restart. Arimo does not support Chinese glyphs. Windows fonts are not necessarily installed on macOS.

## Why can't I click the text?

It may be a scanned image, outlined drawing, hidden OCR layer or an unsupported text structure. The app does not reconstruct these as editable text.

## Why can't I apply a long address?

The replacement may exceed its region or overlap neighboring content. Adjust the region, wrapping or text. Shrink to fit changes the font size.

## Does saving change other content?

The engine removes and replaces selected text while preserving image and vector content. Tests compare untouched regions and pages. A changed PDF is not guaranteed to have the same binary structure or bytes as the source. Check special PDFs with original/edited comparison.

## Are barcodes updated? Is data uploaded?

No. Visible text and encoded barcode data are separate. The app does not regenerate barcodes, upload labels or download fonts at runtime. GitHub hosts only the app and source.

## Which Mac download should I use?

Choose arm64 for Apple M-series chips, x86_64 for Intel; see About This Mac. The supported target is macOS 15 or later. See the [installation guide](guide.en.md#mac-installation) for first-launch checks; the app is not Apple-notarized.

## Why won't the Windows app start?

Use 64-bit Windows 10 / 11 and fully extract the archive, keeping `_internal` next to the EXE. The app is not code-signed with a publisher certificate. Verify the release source and SHA-256 instead of disabling security protections.

## How do I report an issue?

Open an issue with app version, operating system, Mac chip if applicable, steps, expected result and actual result. For font problems include the font name and a minimal PDF with fictitious data. Never attach real names, phone numbers, addresses or tracking details.
