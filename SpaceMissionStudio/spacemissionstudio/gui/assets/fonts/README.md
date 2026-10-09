# IBM Plex (bundled fonts)

The GUI's typeface, as the Carbon design system uses it (UX/UI guidelines,
decision 1). Loaded at start-up by `gui/theme.py`; if a font cannot be
loaded, the platform's own font is used.

| File | Source | SHA-256 |
|---|---|---|
| `IBMPlexSans-Regular.woff`, `IBMPlexSans-Italic.woff`, `IBMPlexSans-SemiBold.woff` | npm `@ibm/plex-sans` 1.1.0, `fonts/complete/woff/` (tarball SHA-256 `c3818979c2a2c82927ea3e7c485e389a18de0b7462887dd4f7acc9a525568962`) | see below |
| `IBMPlexMono-Regular.woff` | npm `@ibm/plex-mono` 2.5.0, `fonts/complete/woff/` (tarball SHA-256 `55b5ffcfcd5e9db36ef2070b2b07a573434ca02c6f3be2b921c0b88fff29acad`) | see below |

```
b731cf56514a4bd711ab2f9acf641f9311707f4386772eb306d25c2b29b73b1a  IBMPlexSans-Regular.woff
ed06e0a2cfa973492c7ee61e5f1bf3be7db4d3d5c1551c889ec458ba2972db99  IBMPlexSans-Italic.woff
fff45f420f0d026b4a39f99b3bfc47dfc06561c598c8db825cfce5fd706bda7a  IBMPlexSans-SemiBold.woff
3a0d6e1587e8dc784be5a75e1c55b1a5533919b04072a29c750bb29cfe4a4b74  IBMPlexMono-Regular.woff
```

The files are IBM's, unmodified. Licence: SIL Open Font License 1.1,
Copyright 2017 IBM Corp., Reserved Font Name "Plex" (`OFL.txt`, identical
in both packages).
