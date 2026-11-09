# Code signing

Tandem's installer isn't signed yet, so Windows SmartScreen warns about it and Smart App Control
blocks it. [SignPath Foundation](https://signpath.org/) signs open-source projects for free.
The release workflow is ready: signing turns on by itself once the secrets below exist.

## What the maintainer does (once)

1. Apply at [signpath.org/apply](https://signpath.org/apply) with the repository link. SignPath
   checks the project (open-source licence, built in public CI) and issues the certificate to
   the maintainer.
2. In SignPath, create a project with the slug `tandem` and a signing policy `release-signing`,
   and link it to this GitHub repository as a trusted build system.
3. In GitHub, repository Settings, Secrets and variables, Actions:
   - secret `SIGNPATH_API_TOKEN`: a SignPath CI user's API token
   - variable `SIGNPATH_ORGANIZATION_ID`: the SignPath organisation id

## What SignPath requires of the project

Done in the repository already, and worth keeping true:

- The README's and every release's "Code signing policy" section, with the SignPath statement,
  the team roles and a link to the privacy policy.
- [docs/privacy-policy.md](privacy-policy.md): what Tandem sends over the internet (two
  lookups, on by default). The installer shows it on its Privacy page and lets the user turn
  both off (`packaging/tandem.iss`, applied with `python -m tandem privacy`).
- Two-factor sign-in for GitHub and SignPath for everyone with access (the maintainer's own
  account setting, not something the repository can show).
- Binary metadata: product name `Tandem`, the same product version in every build
  (`VersionInfo*` in `packaging/tandem.iss`).

## What happens then

On a `v*` tag, `.github/workflows/release.yml` uploads the built installer, SignPath signs it
(after the maintainer approves the request, if the policy asks for that), and the signed file
replaces the unsigned one before the install test and the release. Python's own `python.exe`
and `pythonw.exe` are already signed by the Python Software Foundation.

After signing works, a small signed `Tandem.exe` launcher can replace the `pythonw.exe`
shortcut, so Task Manager shows Tandem's name and icon.
