# Security Policy

Thank you for helping keep Trail Cam Tagger and its users safe.

## Supported versions

Trail Cam Tagger is a small volunteer project. Security fixes are made in the **latest release** only, so please update to the newest version from the [Releases](../../releases) page before reporting.

| Version | Supported |
|---|---|
| Latest release | ✅ |
| Older releases | ❌ |

## Reporting a vulnerability

**Please do not report security problems in public issues, discussions or pull requests.**

Report them privately through GitHub instead:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability** (or use [this link](../../security/advisories/new)).
3. Fill in the form. Only the maintainers can see it.

Please include, as far as you can:
- what the problem is and what an attacker could do with it;
- steps to reproduce it, or a proof of concept;
- the Trail Cam Tagger version, your operating system and your Python version;
- any example file needed to trigger it (attach it privately in the report, never publicly).

## What to expect

This project is run by volunteers, so these are good-faith goals rather than guarantees:
- **Acknowledgement:** within about 7 days.
- **Assessment:** we'll confirm whether it's a security issue and how serious it is, and keep you updated.
- **Fix and release:** as soon as reasonably possible, depending on severity and complexity.
- **Disclosure:** we'll agree on timing with you, and publish a GitHub security advisory once a fixed release is available.
- **Credit:** we're happy to credit you in the advisory and release notes, unless you'd rather stay anonymous.

Please give us a reasonable chance to fix the problem before sharing details publicly.

## Scope

Trail Cam Tagger is an offline desktop app. Things we especially want to hear about:
- A clip, photo or data file that makes the program do something harmful, such as run code, or delete, overwrite or move files.
- Anything that causes files to be moved, renamed or deleted **outside** the Trail Cams folder, or user clips to be lost.
- Problems with how the launcher installs its add-ons on first start.
- Anything that sends data off the computer. The program should make no network connections except downloading its add-ons from PyPI on first start.

Usually out of scope:
- **Vulnerabilities in the add-ons themselves** (OpenCV, Pillow, openpyxl) or in Python. Please report those to their own projects. If one affects Trail Cam Tagger and needs an update or workaround here, do tell us.
- Problems that need someone to already control your computer or user account.
- The program crashing on a broken file without other harm. Please report that as a normal bug.

## Staying safe as a user

- Download Trail Cam Tagger only from this repository's [Releases](../../releases) page.
- Keep Python and the program up to date.
- Keep a backup of clips you care about.
