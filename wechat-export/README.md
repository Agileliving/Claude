# Export a WeChat conversation to a single Word (.docx) file — macOS

Turn a WeChat conversation into a Word document using **free, offline,
open-source tools** on your own Mac. There are two routes; pick based on your
situation:

- **Method A — decrypt WeChat *desktop*'s database (recommended, no cable).**
  Best when you already use WeChat on the Mac and/or want a long history. Reads
  the chats straight from the Mac, no iPhone or cable involved.
- **Method B — iPhone backup + WechatExporter.** Use only if the chats live on
  the phone and are *not* in the Mac desktop app.

Either way, the final `->  .docx` step is done by `html_to_docx.py` in this
folder.

---

## ⚠️ The "which backup is which" trap (read this first)

The word **"backup"** means two completely different things, and only one is
usable:

| | ❌ WeChat's own "Backup to computer" | ✅ What you actually need |
|---|---|---|
| Where | WeChat app → *Backup & Restore* | Method A or B below |
| Produces | An **encrypted** package: folders `ChatPackage`, `Index`, `Media` and files like `pkg_info.dat`, `phoneid.dat`, `d_s.dat`, `backup_time.dat`, `tar_index.dat` | Readable chat data |
| Usable? | **No** — encrypted, restore-only, no chat text inside | Yes |

If what you have looks like the left column (a `ChatPackage`/`Media`/`Index`
folder full of `.dat` files), set it aside — it cannot be converted to text by
any tool. Those files are WeChat's encrypted archive, designed only to be
restored back into WeChat on another phone. Use Method A instead.

---

## Method A — Decrypt WeChat desktop's database with WxEcho (recommended, cable-free)

Uses **WxEcho** (https://github.com/chang-xinhai/WxEcho). It reads the local,
encrypted WeChat desktop database on your Mac and exports a chosen conversation
to TXT/CSV/JSON. Everything stays on your machine.

**Requirements**
- **WeChat for Mac 4.x** (WxEcho supports 4.x, not 3.x). Check via WeChat menu →
  *About WeChat*.
- **Node.js** (for `npm`). Check with `node -v`; if missing, install with
  `brew install node` (or from https://nodejs.org).
- The conversation must actually be present in WeChat **desktop**. If older
  history isn't there, migrate it to the Mac in WeChat first.

**Steps**
```bash
# 1. Install WxEcho
npm install -g @walkerch/wxecho

# 2. Quit WeChat, then re-sign it so its in-memory key can be read.
#    (Removes only the hardened-runtime restriction; no SIP disabling.
#     Reversible by reinstalling WeChat. WeChat must be fully quit first.)
sudo codesign --force --deep --sign - /Applications/WeChat.app

# 3. Reopen WeChat and log in.

# 4. Extract keys and decrypt the local databases.
wxecho keys        # if it errors on permissions, retry with: sudo wxecho keys
wxecho decrypt

# 5. List conversations to find the exact name, then export the one you want.
wxecho export -l
wxecho export -n "Contact Name"        # or:  wxecho export -u <wxid>
```
Note the path of the exported **`.txt`** file, then go to **Convert to Word**
below.

---

## Method B — iPhone backup + WechatExporter (alternative)

Use only if the chats are on the iPhone and not in WeChat desktop.

1. Connect the iPhone, open **Finder**, select the iPhone, choose **"Back up all
   of the data on your iPhone to this Mac,"** **uncheck "Encrypt local backup,"**
   and click **Back Up Now**. (This is an *iPhone* backup — not WeChat's
   "backup to computer", which is the unusable encrypted package above.)
2. Open **WechatExporter** (macOS build,
   https://github.com/BlueMatthew/WechatExporter/releases). It auto-detects the
   Finder backup. Select your account → the single conversation → export as
   **HTML** (or Text).
3. Convert to Word below.

*If Finder never shows the iPhone: it's almost always a **power-only cable**
(swap for a known data cable), an un-trusted phone (unlock it and tap **Trust**),
or a stuck service (restart the Mac). Confirm detection with
`system_profiler SPUSBDataType | grep -i -E 'iphone|apple|mobile'`.*

---

## Convert to Word (.docx)

Run the converter on the file produced by Method A (`.txt`) or Method B
(`.html`/`.txt`):

```bash
cd wechat-export
pip3 install -r requirements.txt                       # installs python-docx (one time)
python3 html_to_docx.py "path/to/exported chat.txt"  chat.docx
# or, for an HTML export:
python3 html_to_docx.py "path/to/exported chat.html" chat.docx
```

You get a single `chat.docx` with every message as a paragraph, ready to open in
Word or Pages.

**Simplest alternative for HTML exports** — if you have pandoc:
```bash
pandoc "exported chat.html" -o chat.docx
```

---

## Try it first on the sample

```bash
python3 html_to_docx.py sample.html sample.docx
open sample.docx
```

## Notes

- The converter uses only the Python standard library plus `python-docx`, fully
  offline.
- Method A needs WeChat **4.x**; for WeChat 3.x on Mac, an older key-extraction
  tool is required (ask and I'll point you to one).
- This exports **your own** chat history — a legitimate personal-data export.
