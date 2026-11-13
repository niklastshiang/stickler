> **Superseded on 2026-11-13.** The authors now publish ENST-Drums openly on Zenodo
> (record 21506051, v2, CC BY-NC-ND 4.0: research only, no commercial use, no redistribution of
> adapted material, cite Gillet & Richard, ISMIR 2006). `stickler fetch enst` downloads it. The
> text below describes the earlier request procedure and is kept for the record.

# Requesting ENST-Drums

ENST-Drums (Gillet & Richard, ISMIR 2006) is a drum dataset from Telecom Paris: three drummers, eight
audio channels per sequence, fully annotated, including "minus one" tracks with accompaniment.
Stickler would use it as a third benchmark dataset next to MDB Drums and the owner's songs.

Source: https://adasp.telecom-paris.fr/resources/2009-11-25-enst-drums/ (checked 2026-11-12)

## Licence in short

The user licence must be **signed and returned** before downloading
([English PDF](http://perso.telecom-paristech.fr/~grichard/ENST-drums/ENST_Drums_License.pdf),
[French PDF](http://perso.telecom-paristech.fr/~grichard/ENST-drums/Licence_ENST_Drums.pdf)).

- Non-exclusive, **strictly personal** right of use, **only for scientific purposes** (the licence
  lists illustration, explanation, teaching, research and analysis).
- **No access for third parties**, no publication of the data (Art. 7-1, Art. 9: the databases are
  confidential).
- **No commercial use** without consent (Art. 7-2).
- **No modification or derived works** without written consent (Art. 7-3). Stickler only reads the
  files and the annotations for evaluation. It does not modify or redistribute them.
- Any published work that uses the data must cite: O. Gillet & G. Richard, "ENST-Drums: an
  extensive audio-visual database for drum signals processing", Proc. ISMIR 2006, Victoria,
  Canada.

Consequences for Stickler: the data lives only in `data/enst/` (gitignored). It never goes into
the repository, a release, the Flatpak or the AppImage. Reports that show ENST numbers cite the
paper.

## Steps for the owner

1. Download the English licence PDF and fill in name, address, phone and email.
2. Sign it and send it back as described on the download page. The link "Download ENST-Drums (I
   HAVE READ AND ACCEPTED THE TERMS OF THE USER LICENCE)" leads to the subscription form
   `https://service.tsi.telecom-paristech.fr/cgi-bin/user-service/subscribe.cgi?ident=ENST%2dDrums&form=&license=1`.
   If the form gives no address for the signed licence, ask the ADASP contact
   (slim.essid@telecom-paris.fr) with the email below.
3. Once access is granted, download `ENST_Drums_Audio1` and unpack it to `data/enst/`.
4. Tell Claude, so that the loader (`stickler fetch enst` reading the local copy) can be built.

## Accompanying email (draft, English)

> Subject: ENST-Drums user licence – request for access
>
> Dear Professor Richard, dear ADASP team,
>
> please find attached my signed user licence for the ENST-Drums database.
>
> I would like to use ENST_Drums_Audio1 for a personal, non-commercial evaluation of open-source
> automatic drum transcription models (onset detection and classification per drum class,
> compared against the annotations). The data will be stored locally only, will not be shared
> with anyone or published, and will not be modified. If I publish results, I will cite
> Gillet & Richard, ISMIR 2006.
>
> Thank you very much for making the database available to the research community.
>
> Kind regards,
> [Name]

## Notes for the evaluation

- YourMT3+ lists ENST-Drums among its training data, and ADT_STR reports results on ENST. Their
  ENST numbers may therefore be optimistic, just as with MDB. The report must say so.
- ENST has separate tracks with and without accompaniment, which makes it a good test for the
  value of drum separation.
