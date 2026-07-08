# Export one WeChat conversation to a single Word (.docx) file — macOS + iPhone

The cheapest, most reliable way to turn a WeChat conversation into a Word
document. All extraction is done by **free, offline, open-source tools** on your
own Mac — no chat text is ever sent to a cloud service or an AI model, so the
cost is essentially zero.

Pipeline:

```
unencrypted iPhone backup  ->  WechatExporter (HTML)  ->  html_to_docx.py  ->  chat.docx
```

---

## About the `.dat` files you uploaded

The five uploaded files (`pkg_info.dat`, `phoneid.dat`, `d_s.dat`,
`phone_history.dat`, `backup_time.dat`) are **not** usable and were set aside:

- `pkg_info.dat` is only backup *metadata* (device name, backup path, a token).
- The other four begin with `RMFH … RMFT` and hold **encrypted** payloads —
  WeChat's "backup to computer" containers, which are designed to be restored
  only back into WeChat, not exported to text. The decryption key lives with
  your account, not in these files.
- All five together are ~1.4 KB; the real message database (MB–GB) isn't even
  present.

There is no cheap way to convert those files. Use the pipeline below instead —
it reads the live data via your iPhone.

---

## Step 1 — Make an *unencrypted* iPhone backup on your Mac

1. Connect the iPhone, open **Finder**, select the iPhone in the sidebar.
2. Choose **"Back up all of the data on your iPhone to this Mac."**
3. **Leave "Encrypt local backup" UNCHECKED** — WechatExporter cannot read
   encrypted backups.
4. Click **Back Up Now** and wait for it to finish.

## Step 2 — Export the one conversation with WechatExporter

1. Download the macOS build of **WechatExporter** (free, open-source):
   https://github.com/BlueMatthew/WechatExporter/releases
2. Open it. It auto-detects the Finder backup from Step 1.
3. Select your WeChat account, find the **single contact/group** you want, and
   select just that conversation.
4. Export as **HTML** (recommended — keeps sender names and timestamps) or as
   **Text**. Note the output folder.

## Step 3 — Convert that export to a Word `.docx`

You have two options; pick whichever is easier for you.

**Option A — one-liner with pandoc** (simplest, if you have pandoc):

```bash
pandoc "path/to/exported chat.html" -o chat.docx
```

Install pandoc with `brew install pandoc` if needed.

**Option B — the included Python script** (no pandoc required):

```bash
cd wechat-export
pip3 install -r requirements.txt          # installs python-docx (one time)
python3 html_to_docx.py "path/to/exported chat.html" chat.docx
```

The script also accepts a `.txt` export:

```bash
python3 html_to_docx.py "path/to/exported chat.txt" chat.docx
```

Either way you get a single `chat.docx` with every message as a paragraph
(sender + timestamp + text), ready to open in Word or Pages.

---

## Try it first on the sample

A tiny `sample.html` is included so you can confirm everything works before
touching your real export:

```bash
python3 html_to_docx.py sample.html sample.docx
open sample.docx      # opens in Word / Pages
```

## Notes

- The script uses only the Python standard library plus `python-docx`, and runs
  fully offline.
- If a future WechatExporter version changes its HTML layout and a message looks
  oddly split or merged, the parser's block-tag handling is at the top of
  `html_to_docx.py` (`_BLOCK_TAGS`) and is easy to adjust — or just use the
  pandoc one-liner.
- This exports **your own** chat history — a legitimate personal-data export.
