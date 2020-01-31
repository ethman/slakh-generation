# Making Slakh2100

This document goes over all of the details needed to recreate the Slakh2100 Dataset.

The original dataset was created using the `lmd-matched` subset of the LMD and
used the 2018 version of Native Instruments' Kontakt Komplete 12 sample pack running through
Kontakt Player 6. All of the patch definition files (`.nkm`, explained further in README.md) are
included in the included directory `kontakt_defs`. Many of these `.nkm` files require patches that
are only available with Kontakt Komplete 12. There is one non-Kontakt patch also needed, which is
[Ample Guitar M Lite II](https://www.amplesound.net/en/pro-pd.asp?id=7).

The included file `config.json` is set up exactly as it was on the machine used to generate
Slakh2100. The only thing you'll need to change is the absolute paths. Slakh2100 used 
`classes_strict.json` as its Instrument Definition Metadata File.