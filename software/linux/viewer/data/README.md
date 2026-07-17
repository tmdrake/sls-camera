# Viewer data

## DrakeVox / Digital Dowsing word list

| File | Description |
|------|-------------|
| `drakevox_words_digitaldowsing.txt` | One word per line (~2k entries), extracted from Digital Dowsing’s published PDF |
| `ovilus_wordlist_digitaldowsing.pdf` | Original PDF as downloaded |

**Source (Digital Dowsing):**

- PDF: http://www.digitaldowsing.com/uploads/pdfguides/ovilus_wordlist.pdf  
- Web: https://www.digitaldowsing.com/word-list/  

PDF title: *Ovilus X, Ovilus II, PX word List Alphabetical*.

**Notes**

- Downloaded for local DrakeVox development/reference. **Ovilus** is Digital Dowsing’s product name; our UI uses **DrakeVox**.
- Check Digital Dowsing’s terms before redistributing in a commercial product.
- **Active bank:** DrakeVox loads `drakevox_words_digitaldowsing.txt` by default
  (`sls_viewer/drakevox.py` → `load_wordlist`). If the file is missing, it falls
  back to the small 20-word classic list in `drakevox.py`.
